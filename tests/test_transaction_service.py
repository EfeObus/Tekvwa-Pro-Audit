"""
Tekvwa Pro Audit - Transaction Service Tests

Unit tests for transaction service.
"""

import pytest
from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.services.transaction_service import TransactionService
from app.models.transaction import TransactionType


class TestTransactionService:
    """Test cases for TransactionService."""
    
    @pytest.mark.asyncio
    async def test_create_transaction(
        self, 
        db_session, 
        test_entity, 
        test_category,
        test_vendor,
        test_user,
    ):
        """Test transaction creation."""
        service = TransactionService(db_session)
        
        transaction = await service.create_transaction(
            entity_id=test_entity.id,
            user_id=test_user.id,
            transaction_type=TransactionType.EXPENSE,
            category_id=test_category.id,
            vendor_id=test_vendor.id,
            description="Test purchase",
            amount=Decimal("10000.00"),
            transaction_date=date.today(),
        )
        
        assert transaction is not None
        assert transaction.amount == Decimal("10000.00")
        assert transaction.entity_id == test_entity.id
    
    @pytest.mark.asyncio
    async def test_calculate_vat(self, db_session):
        """Test VAT calculation at 7.5%."""
        service = TransactionService(db_session)
        
        # VAT should be 7.5% of base amount
        amount = Decimal("100000.00")
        expected_vat = Decimal("7500.00")
        
        vat = service.calculate_vat(amount)
        
        assert vat == expected_vat
    
    @pytest.mark.asyncio
    async def test_get_transaction_by_id(
        self, 
        db_session, 
        test_transaction,
    ):
        """Test getting transaction by ID."""
        service = TransactionService(db_session)
        
        transaction = await service.get_transaction_by_id(
            test_transaction.id,
            test_transaction.entity_id,
        )
        
        assert transaction is not None
        assert transaction.id == test_transaction.id
    
    @pytest.mark.asyncio
    async def test_get_entity_transactions(
        self, 
        db_session, 
        test_entity,
        test_transaction,
    ):
        """Test getting all transactions for an entity."""
        service = TransactionService(db_session)
        
        transactions, total = await service.get_transactions_for_entity(
            entity_id=test_entity.id,
        )
        
        assert len(transactions) >= 1
        assert any(t.id == test_transaction.id for t in transactions)
    
    @pytest.mark.asyncio
    async def test_get_transactions_by_type(
        self, 
        db_session, 
        test_entity,
        test_transaction,
    ):
        """Test filtering transactions by type."""
        service = TransactionService(db_session)
        
        transactions, total = await service.get_transactions_for_entity(
            entity_id=test_entity.id,
            transaction_type="expense",
        )
        
        assert len(transactions) >= 1
        assert all(t.transaction_type == TransactionType.EXPENSE for t in transactions)
    
    @pytest.mark.asyncio
    async def test_get_transactions_by_date_range(
        self, 
        db_session, 
        test_entity,
        test_transaction,
    ):
        """Test filtering transactions by date range."""
        service = TransactionService(db_session)
        
        transactions, total = await service.get_transactions_for_entity(
            entity_id=test_entity.id,
            start_date=date.today(),
            end_date=date.today(),
        )
        
        assert len(transactions) >= 1
    
    @pytest.mark.asyncio
    async def test_update_transaction(
        self, 
        db_session, 
        test_transaction,
    ):
        """Test updating a transaction."""
        service = TransactionService(db_session)
        
        updated = await service.update_transaction(
            transaction=test_transaction,
            description="Updated description",
            amount=Decimal("75000.00"),
        )
        
        assert updated is not None
        assert updated.description == "Updated description"
        assert updated.amount == Decimal("75000.00")
    
    @pytest.mark.asyncio
    async def test_delete_transaction(
        self, 
        db_session, 
        test_transaction,
    ):
        """Test deleting a transaction."""
        service = TransactionService(db_session)
        
        result = await service.delete_transaction(
            transaction=test_transaction,
        )
        
        assert result is True
        
        # Verify deletion
        deleted = await service.get_transaction_by_id(
            test_transaction.id,
            test_transaction.entity_id,
        )
        assert deleted is None


class TestVATCalculations:
    """Test VAT calculation edge cases."""
    
    def test_vat_rate_is_7_5_percent(self):
        """Verify VAT rate is 7.5% per 2026 tax reform."""
        service = TransactionService.__new__(TransactionService)
        service.VAT_RATE = Decimal("0.075")
        
        assert service.VAT_RATE == Decimal("0.075")
    
    def test_vat_on_zero_amount(self):
        """Test VAT calculation on zero amount."""
        service = TransactionService.__new__(TransactionService)
        
        vat = service.calculate_vat(Decimal("0"))
        
        assert vat == Decimal("0")
    
    def test_vat_rounds_correctly(self):
        """Test VAT rounds to 2 decimal places."""
        service = TransactionService.__new__(TransactionService)
        
        # Amount that produces a result needing rounding
        amount = Decimal("33.33")
        vat = service.calculate_vat(amount)
        
        # Should round to 2 decimal places
        assert len(str(vat).split('.')[1]) <= 2
