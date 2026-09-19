"""
Tekvwa Pro Audit - Paystack Provider Tests

Comprehensive tests for Paystack payment integration.
Uses mocked httpx responses to test without real API calls.
"""

import pytest
import pytest_asyncio
import json
import hmac
import hashlib
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.billing_service import (
    PaystackProvider,
    BillingService,
    PaymentStatus,
    PaymentResult,
    BillingCycle,
)
from app.models.sku import SKUTier, IntelligenceAddon, PaymentTransaction
from app.routers.billing import verify_paystack_signature


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def paystack_provider():
    """Create a PaystackProvider with test credentials (mocked, won't make real calls)."""
    return PaystackProvider(
        secret_key="sk_test_mock_123456789",
        base_url="https://api.paystack.co"
    )


@pytest.fixture
def stub_paystack_provider():
    """Create a PaystackProvider in stub mode."""
    # Create provider and manually set stub mode
    provider = PaystackProvider.__new__(PaystackProvider)
    provider.secret_key = ""
    provider.base_url = "https://api.paystack.co"
    provider._is_stub = True
    return provider


@pytest.fixture
def mock_initialize_response():
    """Mock response for initialize_payment."""
    return {
        "status": True,
        "message": "Authorization URL created",
        "data": {
            "authorization_url": "https://checkout.paystack.com/abc123def456",
            "access_code": "abc123def456",
            "reference": "TVP-test1234-20260122120000"
        }
    }


@pytest.fixture
def mock_verify_response_success():
    """Mock response for verify_payment (successful)."""
    return {
        "status": True,
        "message": "Verification successful",
        "data": {
            "id": 12345678,
            "status": "success",
            "reference": "TVP-test1234-20260122120000",
            "amount": 15000000,  # 150,000 Naira in kobo
            "gateway_response": "Successful",
            "paid_at": "2026-01-22T12:30:00.000Z",
            "channel": "card",
            "currency": "NGN",
            "fees": 150000,  # 1,500 Naira in kobo
            "authorization": {
                "card_type": "visa",
                "last4": "4081",
                "exp_month": "12",
                "exp_year": "2028",
                "bank": "Zenith Bank",
                "brand": "visa"
            },
            "customer": {
                "email": "admin@company.com",
                "customer_code": "CUS_abc123"
            },
            "metadata": {
                "organization_id": str(uuid4()),
                "tier": "professional",
                "billing_cycle": "monthly"
            }
        }
    }


@pytest.fixture
def mock_verify_response_failed():
    """Mock response for verify_payment (failed)."""
    return {
        "status": True,
        "message": "Verification successful",
        "data": {
            "id": 12345679,
            "status": "failed",
            "reference": "TVP-failed-20260122120000",
            "amount": 15000000,
            "gateway_response": "Declined",
            "channel": "card",
            "currency": "NGN"
        }
    }


@pytest.fixture
def webhook_payload():
    """Sample Paystack webhook payload for charge.success."""
    return {
        "event": "charge.success",
        "data": {
            "id": 12345678,
            "reference": "TVP-test1234-20260122120000",
            "status": "success",
            "amount": 15000000,
            "gateway_response": "Successful",
            "paid_at": "2026-01-22T12:30:00.000Z",
            "channel": "card",
            "fees": 150000,
            "authorization": {
                "card_type": "visa",
                "last4": "4081",
                "bank": "Zenith Bank",
                "brand": "visa"
            },
            "customer": {
                "email": "admin@company.com",
                "customer_code": "CUS_abc123"
            },
            "metadata": {
                "organization_id": str(uuid4()),
                "tier": "professional",
                "billing_cycle": "monthly"
            }
        }
    }


# =============================================================================
# WEBHOOK SIGNATURE VERIFICATION TESTS
# =============================================================================

class TestWebhookSignatureVerification:
    """Test HMAC-SHA512 signature verification for webhooks."""
    
    def test_valid_signature(self):
        """Test that valid signatures are accepted."""
        secret = "whsec_test_secret_key_12345"
        payload = b'{"event": "charge.success", "data": {}}'
        
        # Calculate expected signature
        signature = hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()
        
        assert verify_paystack_signature(payload, signature, secret) is True
    
    def test_invalid_signature(self):
        """Test that invalid signatures are rejected."""
        secret = "whsec_test_secret_key_12345"
        payload = b'{"event": "charge.success", "data": {}}'
        
        assert verify_paystack_signature(payload, "invalid_signature", secret) is False
    
    def test_empty_signature(self):
        """Test that empty signatures are rejected."""
        secret = "whsec_test_secret_key_12345"
        payload = b'{"event": "charge.success", "data": {}}'
        
        assert verify_paystack_signature(payload, "", secret) is False
    
    def test_empty_secret(self):
        """Test that empty secrets reject all signatures."""
        payload = b'{"event": "charge.success", "data": {}}'
        signature = "any_signature"
        
        assert verify_paystack_signature(payload, signature, "") is False
    
    def test_tampered_payload(self):
        """Test that modified payloads are detected."""
        secret = "whsec_test_secret_key_12345"
        original_payload = b'{"event": "charge.success", "data": {"amount": 100}}'
        tampered_payload = b'{"event": "charge.success", "data": {"amount": 1000000}}'
        
        # Sign original payload
        signature = hmac.new(
            secret.encode('utf-8'),
            original_payload,
            hashlib.sha512
        ).hexdigest()
        
        # Verify fails with tampered payload
        assert verify_paystack_signature(tampered_payload, signature, secret) is False


# =============================================================================
# PAYSTACK PROVIDER TESTS
# =============================================================================

class TestPaystackProviderStubMode:
    """Test PaystackProvider in stub mode."""
    
    @pytest.mark.asyncio
    async def test_stub_initialize_payment(self, stub_paystack_provider):
        """Test initialize_payment returns stub data."""
        result = await stub_paystack_provider.initialize_payment(
            email="test@example.com",
            amount_naira=150000,
            reference="TVP-stub-test",
            callback_url="https://example.com/callback"
        )
        
        assert result["status"] is True
        assert "STUB MODE" in result["message"]
        assert result["data"]["reference"] == "TVP-stub-test"
        assert "stub" in result["data"]["authorization_url"]
    
    @pytest.mark.asyncio
    async def test_stub_verify_payment(self, stub_paystack_provider):
        """Test verify_payment returns stub success."""
        result = await stub_paystack_provider.verify_payment("TVP-stub-test")
        
        assert result.success is True
        assert result.status == PaymentStatus.SUCCESS
        assert result.reference == "TVP-stub-test"
        assert result.metadata.get("stub") is True
    
    @pytest.mark.asyncio
    async def test_stub_create_subscription(self, stub_paystack_provider):
        """Test create_subscription returns stub data."""
        result = await stub_paystack_provider.create_subscription(
            customer_email="test@example.com",
            plan_code="PLN_professional"
        )
        
        assert result["status"] is True
        assert "STUB MODE" in result["message"]
        assert "stub_sub_" in result["data"]["subscription_code"]
    
    @pytest.mark.asyncio
    async def test_stub_cancel_subscription(self, stub_paystack_provider):
        """Test cancel_subscription returns stub success."""
        result = await stub_paystack_provider.cancel_subscription(
            subscription_code="SUB_123",
            token="token_123"
        )
        
        assert result["status"] is True
        assert "STUB MODE" in result["message"]
    
    @pytest.mark.asyncio
    async def test_stub_refund_payment(self, stub_paystack_provider):
        """Test refund_payment returns stub data."""
        result = await stub_paystack_provider.refund_payment(
            transaction_reference="TVP-stub-test"
        )
        
        assert result["status"] is True
        assert "STUB MODE" in result["message"]
        assert "stub_refund_" in result["data"]["refund_id"]


class TestPaystackProviderRealMode:
    """Test PaystackProvider with mocked HTTP responses."""
    
    @pytest.mark.asyncio
    async def test_initialize_payment_success(self, paystack_provider, mock_initialize_response):
        """Test successful payment initialization."""
        with patch('httpx.AsyncClient') as MockClient:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_initialize_response
            mock_client.request = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__.return_value = mock_client
            
            result = await paystack_provider.initialize_payment(
                email="admin@company.com",
                amount_naira=150000,
                reference="TVP-test1234-20260122120000",
                callback_url="https://app.tekvwa.com/billing/callback"
            )
            
            assert result["status"] is True
            assert result["data"]["authorization_url"].startswith("https://checkout.paystack.com/")
            assert result["data"]["reference"] == "TVP-test1234-20260122120000"
    
    @pytest.mark.asyncio
    async def test_verify_payment_success(self, paystack_provider, mock_verify_response_success):
        """Test successful payment verification."""
        with patch('httpx.AsyncClient') as MockClient:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_verify_response_success
            mock_client.request = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__.return_value = mock_client
            
            result = await paystack_provider.verify_payment("TVP-test1234-20260122120000")
            
            assert result.success is True
            assert result.status == PaymentStatus.SUCCESS
            assert result.amount_naira == 150000  # Converted from kobo
            assert result.metadata["last4"] == "4081"
            assert result.metadata["card_type"] == "visa"
    
    @pytest.mark.asyncio
    async def test_verify_payment_failed(self, paystack_provider, mock_verify_response_failed):
        """Test failed payment verification."""
        with patch('httpx.AsyncClient') as MockClient:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_verify_response_failed
            mock_client.request = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__.return_value = mock_client
            
            result = await paystack_provider.verify_payment("TVP-failed-20260122120000")
            
            assert result.success is False
            assert result.status == PaymentStatus.FAILED
    
    @pytest.mark.asyncio
    async def test_api_timeout_handling(self, paystack_provider):
        """Test timeout error handling."""
        import httpx
        
        with patch('httpx.AsyncClient') as MockClient:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            MockClient.return_value.__aenter__.return_value = mock_client
            
            result = await paystack_provider.initialize_payment(
                email="test@example.com",
                amount_naira=50000,
                reference="TVP-timeout-test",
                callback_url="https://example.com/callback"
            )
            
            assert result["status"] is False
            assert "timed out" in result["message"].lower()
    
    @pytest.mark.asyncio
    async def test_api_network_error_handling(self, paystack_provider):
        """Test network error handling."""
        import httpx
        
        with patch('httpx.AsyncClient') as MockClient:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(side_effect=httpx.RequestError("Network error"))
            MockClient.return_value.__aenter__.return_value = mock_client
            
            result = await paystack_provider.initialize_payment(
                email="test@example.com",
                amount_naira=50000,
                reference="TVP-network-test",
                callback_url="https://example.com/callback"
            )
            
            assert result["status"] is False
            assert "network error" in result["message"].lower()


# =============================================================================
# BILLING SERVICE TESTS
# =============================================================================

class TestBillingServicePricing:
    """Test billing service pricing calculations."""
    
    def test_calculate_core_monthly_price(self, db_session):
        """Test Core tier monthly pricing."""
        service = BillingService(db_session)
        price = service.calculate_subscription_price(
            tier=SKUTier.CORE,
            billing_cycle=BillingCycle.MONTHLY
        )
        
        # Core tier starts at ₦25,000/month
        assert price >= 25000
    
    def test_calculate_professional_annual_price(self, db_session):
        """Test Professional tier annual pricing."""
        service = BillingService(db_session)
        price = service.calculate_subscription_price(
            tier=SKUTier.PROFESSIONAL,
            billing_cycle=BillingCycle.ANNUAL
        )
        
        # Professional annual should be less than 12x monthly (discount)
        monthly_price = service.calculate_subscription_price(
            tier=SKUTier.PROFESSIONAL,
            billing_cycle=BillingCycle.MONTHLY
        )
        
        # Annual should be roughly 10 months (20% discount)
        assert price < monthly_price * 12
    
    def test_calculate_price_with_additional_users(self, db_session):
        """Test pricing with additional users."""
        service = BillingService(db_session)
        
        base_price = service.calculate_subscription_price(
            tier=SKUTier.PROFESSIONAL,
            billing_cycle=BillingCycle.MONTHLY,
            additional_users=0
        )
        
        with_users = service.calculate_subscription_price(
            tier=SKUTier.PROFESSIONAL,
            billing_cycle=BillingCycle.MONTHLY,
            additional_users=5
        )
        
        assert with_users > base_price
    
    def test_calculate_price_with_intelligence_addon(self, db_session):
        """Test pricing with intelligence add-on."""
        service = BillingService(db_session)
        
        base_price = service.calculate_subscription_price(
            tier=SKUTier.PROFESSIONAL,
            billing_cycle=BillingCycle.MONTHLY,
            intelligence_addon=IntelligenceAddon.NONE
        )
        
        with_addon = service.calculate_subscription_price(
            tier=SKUTier.PROFESSIONAL,
            billing_cycle=BillingCycle.MONTHLY,
            intelligence_addon=IntelligenceAddon.STANDARD
        )
        
        assert with_addon > base_price


# =============================================================================
# PAYMENT TRANSACTION MODEL TESTS
# =============================================================================

class TestPaymentTransactionModel:
    """Test PaymentTransaction model properties and methods."""
    
    def test_amount_naira_property(self):
        """Test amount_naira conversion from kobo."""
        tx = PaymentTransaction(
            reference="TVP-test-123",
            amount_kobo=15000000,  # 150,000 Naira
            status="pending"
        )
        
        assert tx.amount_naira == 150000
    
    def test_amount_naira_formatted_property(self):
        """Test formatted amount in Naira."""
        tx = PaymentTransaction(
            reference="TVP-test-123",
            amount_kobo=15000000,  # 150,000 Naira
            status="pending"
        )
        
        # Check format is ₦150,000 (no decimals since property uses int)
        assert "150,000" in tx.amount_naira_formatted
        assert "₦" in tx.amount_naira_formatted
    
    def test_fee_naira_property(self):
        """Test fee conversion from kobo."""
        tx = PaymentTransaction(
            reference="TVP-test-123",
            amount_kobo=15000000,
            paystack_fee_kobo=150000,  # 1,500 Naira - using correct field name
            status="success"
        )
        
        assert tx.fee_naira == 1500
    
    def test_fee_naira_none_when_no_fee(self):
        """Test fee_naira returns None when no fee set."""
        tx = PaymentTransaction(
            reference="TVP-test-123",
            amount_kobo=15000000,
            status="pending"
        )
        
        assert tx.fee_naira is None
    
    def test_to_dict_method(self):
        """Test to_dict serialization."""
        tx = PaymentTransaction(
            reference="TVP-test-123",
            amount_kobo=15000000,
            currency="NGN",
            status="success",
            tier=SKUTier.PROFESSIONAL,  # Use enum
            billing_cycle="monthly"
        )
        
        result = tx.to_dict()
        
        assert result["reference"] == "TVP-test-123"
        assert result["amount_naira"] == 150000
        assert result["status"] == "success"
        assert result["tier"] == "professional"  # Should convert enum to value


# =============================================================================
# INTEGRATION TESTS (with fixtures)
# =============================================================================

@pytest_asyncio.fixture
async def db_session():
    """Minimal db session fixture for unit tests."""
    # Create a mock session for unit testing
    from unittest.mock import AsyncMock
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    yield session


class TestBillingServiceIntegration:
    """Integration tests for BillingService with database."""
    
    @pytest.mark.asyncio
    async def test_create_payment_intent_creates_transaction(self, db_session):
        """Test that create_payment_intent saves a PaymentTransaction."""
        # Use stub provider to avoid real API calls
        stub_provider = PaystackProvider(secret_key="")
        service = BillingService(db_session, payment_provider=stub_provider)
        
        org_id = uuid4()
        
        intent = await service.create_payment_intent(
            organization_id=org_id,
            tier=SKUTier.PROFESSIONAL,
            billing_cycle=BillingCycle.MONTHLY,
            admin_email="admin@company.com"
        )
        
        # Verify db.add was called
        db_session.add.assert_called_once()
        
        # Verify PaymentIntent was returned
        assert intent.reference.startswith("TVP-")
        assert intent.tier == SKUTier.PROFESSIONAL
        assert intent.status == PaymentStatus.PENDING


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
