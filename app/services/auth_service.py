"""
Tekvwa Pro Audit - Authentication Service

Business logic for user authentication and registration.
"""

import uuid
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User, UserRole, UserEntityAccess
from app.models.organization import Organization, SubscriptionTier
from app.models.entity import BusinessEntity
from app.utils.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    create_password_reset_token,
    verify_password_reset_token,
    verify_access_token,
    create_email_verification_token,
    verify_email_verification_token,
)
from app.config import settings


class AuthService:
    """Service for authentication operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email address."""
        result = await self.db.execute(
            select(User)
            .options(
                selectinload(User.organization),
                selectinload(User.entity_access).selectinload(UserEntityAccess.entity)
            )
            .where(User.email == email.lower())
        )
        return result.scalar_one_or_none()
    
    async def get_user_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        """Get user by ID."""
        result = await self.db.execute(
            select(User)
            .options(
                selectinload(User.organization),
                selectinload(User.entity_access).selectinload(UserEntityAccess.entity)
            )
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def authenticate_user(
        self, email: str, password: str
    ) -> Optional[User]:
        """
        Authenticate user with email and password.
        
        Returns:
            User if authentication successful, None otherwise
        """
        user = await self.get_user_by_email(email)
        
        if not user:
            return None
        
        if not verify_password(password, user.hashed_password):
            return None
        
        return user
    
    async def register_user(
        self,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        organization_name: str,
        phone_number: Optional[str] = None,
        # New comprehensive registration fields
        account_type: str = "individual",
        street_address: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        lga: Optional[str] = None,
        postal_code: Optional[str] = None,
        country: str = "Nigeria",
        tin: Optional[str] = None,
        cac_registration_number: Optional[str] = None,
        cac_registration_type: Optional[str] = None,
        date_of_incorporation: Optional[str] = None,
        nin: Optional[str] = None,
        industry: Optional[str] = None,
        employee_count: Optional[str] = None,
        annual_revenue_range: Optional[str] = None,
        school_type: Optional[str] = None,
        moe_registration_number: Optional[str] = None,
        scuml_registration: Optional[str] = None,
        mission_statement: Optional[str] = None,
        referral_code: Optional[str] = None,
    ) -> Tuple[User, Organization, BusinessEntity]:
        """
        Register a new user with organization and default entity.
        
        Supports comprehensive registration for different account types:
        - Individual: Personal accounts with minimal requirements
        - Small Business: Micro businesses with BN registration
        - SME: Small & Medium Enterprises with RC registration
        - School: Educational institutions
        - Non-Profit: NGOs with IT registration
        - Corporation: Large companies
        
        Returns:
            Tuple of (User, Organization, BusinessEntity)
        """
        from app.models.organization import OrganizationType
        
        # Check if email already exists
        existing_user = await self.get_user_by_email(email)
        if existing_user:
            raise ValueError("Email already registered")
        
        # Map account type string to enum
        account_type_map = {
            "individual": OrganizationType.INDIVIDUAL,
            "small_business": OrganizationType.SMALL_BUSINESS,
            "sme": OrganizationType.SME,
            "school": OrganizationType.SCHOOL,
            "non_profit": OrganizationType.NON_PROFIT,
            "corporation": OrganizationType.CORPORATION,
        }
        org_type = account_type_map.get(account_type, OrganizationType.INDIVIDUAL)
        
        # Build full address string
        address_parts = [p for p in [street_address, lga, city, state, postal_code, country] if p]
        full_address = ", ".join(address_parts) if address_parts else None
        
        # Create organization
        org_slug = self._generate_slug(organization_name)
        organization = Organization(
            name=organization_name,
            slug=org_slug,
            email=email.lower(),
            phone=phone_number,
            subscription_tier=SubscriptionTier.FREE,
            organization_type=org_type,
            referred_by_code=referral_code,
        )
        self.db.add(organization)
        await self.db.flush()  # Get organization ID
        
        # Create default business entity with comprehensive info
        # Note: Additional details (industry, employee count, etc.) stored in organization metadata
        entity = BusinessEntity(
            organization_id=organization.id,
            name=organization_name,
            legal_name=organization_name,
            country=country,
            currency="NGN",
            fiscal_year_start_month=1,
            # Address fields
            address_line1=street_address,
            city=city,
            state=state,
            lga=lga,  # Store LGA in dedicated column
            # Nigerian compliance fields
            tin=tin,
            rc_number=cac_registration_number,  # CAC RC/BN/IT number
        )
        self.db.add(entity)
        await self.db.flush()  # Get entity ID
        
        # Create user
        # Self-registered users require email verification
        user = User(
            email=email.lower(),
            hashed_password=get_password_hash(password),
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            organization_id=organization.id,
            role=UserRole.OWNER,
            is_active=True,
            is_verified=False,  # Will be verified via email
            is_invited_user=False,  # Self-registered users must verify email
        )
        self.db.add(user)
        await self.db.flush()  # Get user ID
        
        # Grant user access to default entity
        entity_access = UserEntityAccess(
            user_id=user.id,
            entity_id=entity.id,
            can_write=True,
            can_delete=True,
        )
        self.db.add(entity_access)
        
        # Create TenantSKU record - all new registrations start on Core tier
        # This enables the commercial SKU system for feature gating
        from app.models.sku import TenantSKU, SKUTier
        from datetime import date as date_type
        
        today = date_type.today()
        # 14-day trial of Core tier
        trial_end = datetime.utcnow() + timedelta(days=14)
        # Calculate next month for billing period end
        if today.month == 12:
            period_end = date_type(today.year + 1, 1, today.day)
        else:
            # Handle months with fewer days
            try:
                period_end = date_type(today.year, today.month + 1, today.day)
            except ValueError:
                # Day doesn't exist in next month (e.g., Jan 31 -> Feb 28)
                if today.month + 1 == 2:
                    period_end = date_type(today.year, 2, 28)
                else:
                    period_end = date_type(today.year, today.month + 1, 28)
        
        tenant_sku = TenantSKU(
            organization_id=organization.id,
            tier=SKUTier.CORE,
            intelligence_addon=None,
            is_active=True,
            billing_cycle="monthly",
            trial_ends_at=trial_end,
            current_period_start=today,
            current_period_end=period_end,
            notes=f"Auto-created during registration. Account type: {account_type}",
        )
        self.db.add(tenant_sku)
        
        await self.db.commit()
        await self.db.refresh(user)
        await self.db.refresh(organization)
        await self.db.refresh(entity)
        
        return user, organization, entity
    
    def _build_entity_notes(
        self,
        account_type: str,
        industry: Optional[str] = None,
        employee_count: Optional[str] = None,
        annual_revenue_range: Optional[str] = None,
        school_type: Optional[str] = None,
        scuml_registration: Optional[str] = None,
        mission_statement: Optional[str] = None,
        date_of_incorporation: Optional[str] = None,
        cac_registration_type: Optional[str] = None,
        nin: Optional[str] = None,
    ) -> Optional[str]:
        """Build structured notes with additional registration info."""
        import json
        
        data = {
            "account_type": account_type,
            "registration_date": datetime.utcnow().isoformat(),
        }
        
        if industry:
            data["industry"] = industry
        if employee_count:
            data["employee_count"] = employee_count
        if annual_revenue_range:
            data["annual_revenue_range"] = annual_revenue_range
        if school_type:
            data["school_type"] = school_type
        if scuml_registration:
            data["scuml_registration"] = scuml_registration
        if mission_statement:
            data["mission_statement"] = mission_statement
        if date_of_incorporation:
            data["date_of_incorporation"] = date_of_incorporation
        if cac_registration_type:
            data["cac_registration_type"] = cac_registration_type
        if nin:
            data["nin"] = nin  # Stored securely for Individual accounts
        
        return json.dumps(data) if len(data) > 2 else None
    
    def create_tokens(self, user: User) -> dict:
        """
        Create access and refresh tokens for user.
        
        Returns:
            Dictionary with access_token, refresh_token, token_type, expires_in
        """
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "org_id": str(user.organization_id) if user.organization_id else None,
            "role": user.role.value if user.role else None,
            # Include platform staff info for proper authorization
            "is_platform_staff": user.is_platform_staff,
            "platform_role": user.platform_role.value if user.platform_role else None,
        }
        
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
        }
    
    async def change_password(
        self,
        user: User,
        current_password: str,
        new_password: str,
    ) -> bool:
        """
        Change user password.
        
        Returns:
            True if password changed successfully
        """
        if not verify_password(current_password, user.hashed_password):
            raise ValueError("Current password is incorrect")
        
        user.hashed_password = get_password_hash(new_password)
        user.must_reset_password = False  # Clear the flag after password change
        await self.db.commit()
        
        return True
    
    def _generate_slug(self, name: str) -> str:
        """Generate URL-friendly slug from name."""
        # Convert to lowercase and replace spaces with hyphens
        slug = name.lower().strip()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[\s_-]+', '-', slug)
        slug = slug.strip('-')
        
        # Add random suffix to ensure uniqueness
        suffix = uuid.uuid4().hex[:6]
        return f"{slug}-{suffix}"
    
    def create_password_reset_token(self, user: User) -> str:
        """
        Create a password reset token for user.
        
        Returns:
            Password reset token string
        """
        token_data = {
            "sub": str(user.id),
            "email": user.email,
        }
        return create_password_reset_token(token_data)
    
    async def reset_password_with_token(
        self,
        token: str,
        new_password: str,
    ) -> bool:
        """
        Reset user password using reset token.
        
        Returns:
            True if password reset successfully
        """
        payload = verify_password_reset_token(token)
        
        if not payload:
            raise ValueError("Invalid or expired reset token")
        
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Invalid token payload")
        
        user = await self.get_user_by_id(uuid.UUID(user_id))
        
        if not user:
            raise ValueError("User not found")
        
        user.hashed_password = get_password_hash(new_password)
        user.must_reset_password = False  # Clear the flag after password reset
        await self.db.commit()
        
        return True
    
    async def get_current_user_from_token(self, token: str) -> Optional[User]:
        """
        Get the current user from an access token.
        
        Args:
            token: JWT access token string
            
        Returns:
            User object if token is valid and user exists, None otherwise
        """
        payload = verify_access_token(token)
        
        if not payload:
            return None
        
        user_id = payload.get("sub")
        if not user_id:
            return None
        
        try:
            user = await self.get_user_by_id(uuid.UUID(user_id))
            return user
        except (ValueError, TypeError):
            return None

    def create_email_verification_token(self, user: User) -> str:
        """
        Create an email verification token for user.
        Stores the token in the user record for later verification.
        
        Returns:
            Email verification token string
        """
        from datetime import datetime
        
        token_data = {
            "sub": str(user.id),
            "email": user.email,
        }
        token = create_email_verification_token(token_data)
        
        # Store token in user record for tracking
        user.email_verification_token = token
        user.email_verification_sent_at = datetime.utcnow()
        
        return token
    
    async def verify_email_with_token(self, token: str) -> bool:
        """
        Verify user email using verification token.
        
        Returns:
            True if email verified successfully
        """
        from datetime import datetime
        
        payload = verify_email_verification_token(token)
        
        if not payload:
            raise ValueError("Invalid or expired verification token")
        
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Invalid token payload")
        
        user = await self.get_user_by_id(uuid.UUID(user_id))
        
        if not user:
            raise ValueError("User not found")
        
        if user.is_verified:
            raise ValueError("Email is already verified")
        
        # Mark email as verified
        user.is_verified = True
        user.email_verified_at = datetime.utcnow()
        user.email_verification_token = None  # Clear the token
        
        await self.db.commit()
        
        return True
    
    async def resend_verification_email(self, email: str) -> Optional[User]:
        """
        Get user by email for resending verification email.
        
        Returns:
            User if found and not verified, None otherwise
        """
        user = await self.get_user_by_email(email)
        
        if not user:
            return None
        
        if user.is_verified:
            return None  # Already verified
        
        return user
