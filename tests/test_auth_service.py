"""
Tekvwa Pro Audit - Auth Service Tests

Unit tests for authentication service.
"""

import pytest
from datetime import datetime
from uuid import uuid4

from app.services.auth_service import AuthService
from app.models.user import User


class TestAuthService:
    """Test cases for AuthService."""
    
    @pytest.mark.asyncio
    async def test_create_user(self, db_session):
        """Test user creation via register_user."""
        service = AuthService(db_session)
        
        # Note: register_user returns (user, organization, entity) tuple
        user, org, entity = await service.register_user(
            email="createduser@example.com",
            password="SecurePassword123!",
            first_name="New",
            last_name="User",
            organization_name="Test Org",
        )
        
        assert user is not None
        assert user.email == "createduser@example.com"
        assert user.first_name == "New"
        assert user.last_name == "User"
        assert user.hashed_password != "SecurePassword123!"  # Should be hashed
    
    @pytest.mark.asyncio
    async def test_authenticate_user_success(self, db_session, test_user):
        """Test successful user authentication."""
        service = AuthService(db_session)
        
        user = await service.authenticate_user(
            email="testuser@example.com",
            password="TestPassword123!",
        )
        
        assert user is not None
        assert user.email == "testuser@example.com"
    
    @pytest.mark.asyncio
    async def test_authenticate_user_wrong_password(self, db_session, test_user):
        """Test authentication with wrong password."""
        service = AuthService(db_session)
        
        user = await service.authenticate_user(
            email="testuser@example.com",
            password="WrongPassword!",
        )
        
        assert user is None
    
    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(self, db_session):
        """Test authentication with non-existent user."""
        service = AuthService(db_session)
        
        user = await service.authenticate_user(
            email="nonexistent@example.com",
            password="Password123!",
        )
        
        assert user is None
    
    @pytest.mark.asyncio
    async def test_get_user_by_id(self, db_session, test_user):
        """Test getting user by ID."""
        service = AuthService(db_session)
        
        user = await service.get_user_by_id(test_user.id)
        
        assert user is not None
        assert user.id == test_user.id
        assert user.email == test_user.email
    
    @pytest.mark.asyncio
    async def test_get_user_by_email(self, db_session, test_user):
        """Test getting user by email."""
        service = AuthService(db_session)
        
        user = await service.get_user_by_email("testuser@example.com")
        
        assert user is not None
        assert user.email == "testuser@example.com"
    
    @pytest.mark.asyncio
    async def test_update_user(self, db_session, test_user):
        """Test updating user details via direct model update."""
        # Direct update since no update_user method exists
        test_user.first_name = "Updated"
        test_user.last_name = "Name"
        db_session.add(test_user)
        await db_session.commit()
        await db_session.refresh(test_user)
        
        assert test_user.first_name == "Updated"
        assert test_user.last_name == "Name"
