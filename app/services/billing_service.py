"""
Tekvwa Pro Audit - Billing Service

Service for managing billing, subscriptions, and payments.
Primary payment provider: Paystack (for Nigerian Naira transactions).

This is a stub implementation providing the interface for:
- Subscription management
- Payment processing
- Invoice generation
- Payment webhooks
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Dict, List, Optional, Any
from uuid import UUID
from enum import Enum
from dataclasses import dataclass

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sku import TenantSKU, SKUTier, IntelligenceAddon, PaymentTransaction
from app.config.sku_config import TIER_PRICING, INTELLIGENCE_PRICING

logger = logging.getLogger(__name__)


# =============================================================================
# BILLING ERROR CODES (#46)
# =============================================================================

class BillingErrorCode(str, Enum):
    """
    Structured error codes for billing failures.
    
    Similar to NRSErrorCode, provides machine-readable codes for:
    - Frontend error handling
    - Logging and analytics
    - Customer support troubleshooting
    """
    # Success
    SUCCESS = "B000"
    
    # Network/Connection Errors (B1xx)
    NETWORK_ERROR = "B100"
    TIMEOUT_ERROR = "B101"
    CONNECTION_REFUSED = "B102"
    SSL_ERROR = "B103"
    
    # Validation Errors (B2xx)
    INVALID_AMOUNT = "B200"
    AMOUNT_TOO_LOW = "B201"
    AMOUNT_TOO_HIGH = "B202"
    INVALID_EMAIL = "B203"
    INVALID_REFERENCE = "B204"
    INVALID_CURRENCY = "B205"
    INVALID_TIER = "B206"
    
    # Payment Errors (B3xx)
    PAYMENT_FAILED = "B300"
    CARD_DECLINED = "B301"
    INSUFFICIENT_FUNDS = "B302"
    EXPIRED_CARD = "B303"
    INVALID_CARD = "B304"
    CARD_NOT_SUPPORTED = "B305"
    BANK_ERROR = "B306"
    TRANSACTION_DECLINED = "B307"
    
    # Authorization Errors (B4xx)
    UNAUTHORIZED = "B400"
    INVALID_API_KEY = "B401"
    WEBHOOK_VERIFICATION_FAILED = "B402"
    
    # Transaction Errors (B5xx)
    TRANSACTION_NOT_FOUND = "B500"
    DUPLICATE_TRANSACTION = "B501"
    TRANSACTION_EXPIRED = "B502"
    ALREADY_PROCESSED = "B503"
    REFUND_FAILED = "B504"
    PARTIAL_REFUND_NOT_ALLOWED = "B505"
    DUPLICATE_WEBHOOK = "B506"
    
    # Subscription Errors (B6xx)
    SUBSCRIPTION_NOT_FOUND = "B600"
    SUBSCRIPTION_CANCELLED = "B601"
    SUBSCRIPTION_EXPIRED = "B602"
    PLAN_NOT_FOUND = "B603"
    DOWNGRADE_NOT_ALLOWED = "B604"
    INVALID_PLAN_CHANGE = "B605"
    
    # Provider Errors (B7xx)
    PROVIDER_ERROR = "B700"
    PROVIDER_UNAVAILABLE = "B701"
    RATE_LIMITED = "B702"
    
    # Internal Errors (B9xx)
    INTERNAL_ERROR = "B900"
    DATABASE_ERROR = "B901"
    CONFIGURATION_ERROR = "B902"
    UNEXPECTED_ERROR = "B999"


# Mapping of error codes to user-friendly messages
BILLING_ERROR_MESSAGES = {
    BillingErrorCode.SUCCESS: "Payment successful",
    BillingErrorCode.NETWORK_ERROR: "Network error occurred. Please try again.",
    BillingErrorCode.TIMEOUT_ERROR: "Request timed out. Please try again.",
    BillingErrorCode.CONNECTION_REFUSED: "Could not connect to payment provider.",
    BillingErrorCode.SSL_ERROR: "Secure connection error.",
    BillingErrorCode.INVALID_AMOUNT: "Invalid payment amount.",
    BillingErrorCode.AMOUNT_TOO_LOW: "Payment amount is below minimum allowed.",
    BillingErrorCode.AMOUNT_TOO_HIGH: "Payment amount exceeds maximum allowed.",
    BillingErrorCode.INVALID_EMAIL: "Invalid email address.",
    BillingErrorCode.INVALID_REFERENCE: "Invalid payment reference.",
    BillingErrorCode.INVALID_CURRENCY: "Currency not supported.",
    BillingErrorCode.INVALID_TIER: "Invalid subscription tier.",
    BillingErrorCode.PAYMENT_FAILED: "Payment failed. Please try again.",
    BillingErrorCode.CARD_DECLINED: "Card was declined. Please use a different card.",
    BillingErrorCode.INSUFFICIENT_FUNDS: "Insufficient funds. Please use a different payment method.",
    BillingErrorCode.EXPIRED_CARD: "Card has expired. Please use a different card.",
    BillingErrorCode.INVALID_CARD: "Invalid card details.",
    BillingErrorCode.CARD_NOT_SUPPORTED: "Card type not supported.",
    BillingErrorCode.BANK_ERROR: "Bank error occurred. Please try again.",
    BillingErrorCode.TRANSACTION_DECLINED: "Transaction was declined.",
    BillingErrorCode.UNAUTHORIZED: "Unauthorized access.",
    BillingErrorCode.INVALID_API_KEY: "Invalid API key.",
    BillingErrorCode.WEBHOOK_VERIFICATION_FAILED: "Webhook verification failed.",
    BillingErrorCode.TRANSACTION_NOT_FOUND: "Transaction not found.",
    BillingErrorCode.DUPLICATE_TRANSACTION: "Duplicate transaction detected.",
    BillingErrorCode.TRANSACTION_EXPIRED: "Transaction has expired.",
    BillingErrorCode.ALREADY_PROCESSED: "Transaction already processed.",
    BillingErrorCode.REFUND_FAILED: "Refund failed.",
    BillingErrorCode.PARTIAL_REFUND_NOT_ALLOWED: "Partial refund not allowed.",
    BillingErrorCode.DUPLICATE_WEBHOOK: "Duplicate webhook event already processed.",
    BillingErrorCode.SUBSCRIPTION_NOT_FOUND: "Subscription not found.",
    BillingErrorCode.SUBSCRIPTION_CANCELLED: "Subscription has been cancelled.",
    BillingErrorCode.SUBSCRIPTION_EXPIRED: "Subscription has expired.",
    BillingErrorCode.PLAN_NOT_FOUND: "Subscription plan not found.",
    BillingErrorCode.DOWNGRADE_NOT_ALLOWED: "Downgrade not allowed at this time.",
    BillingErrorCode.INVALID_PLAN_CHANGE: "Invalid plan change requested.",
    BillingErrorCode.PROVIDER_ERROR: "Payment provider error.",
    BillingErrorCode.PROVIDER_UNAVAILABLE: "Payment provider temporarily unavailable.",
    BillingErrorCode.RATE_LIMITED: "Too many requests. Please wait and try again.",
    BillingErrorCode.INTERNAL_ERROR: "Internal error occurred.",
    BillingErrorCode.DATABASE_ERROR: "Database error occurred.",
    BillingErrorCode.CONFIGURATION_ERROR: "Configuration error.",
    BillingErrorCode.UNEXPECTED_ERROR: "An unexpected error occurred.",
}


def get_error_message(code: BillingErrorCode) -> str:
    """Get user-friendly message for an error code."""
    return BILLING_ERROR_MESSAGES.get(code, "An error occurred.")


@dataclass
class BillingError:
    """Structured billing error with code and message."""
    code: BillingErrorCode
    message: str
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_code": self.code.value,
            "error_name": self.code.name,
            "message": self.message,
            "details": self.details,
        }


# =============================================================================
# BILLING CONFIGURATION CONSTANTS
# =============================================================================

# Amount validation limits (in Naira)
MIN_PAYMENT_AMOUNT = 100  # Minimum ₦100
MAX_PAYMENT_AMOUNT = 50_000_000  # Maximum ₦50 million


# =============================================================================
# ENUMS AND DATA CLASSES
# =============================================================================

class PaymentStatus(str, Enum):
    """Payment transaction status."""
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class PaymentMethod(str, Enum):
    """Payment methods available."""
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    USSD = "ussd"
    MOBILE_MONEY = "mobile_money"


class BillingCycle(str, Enum):
    """Billing cycle options."""
    MONTHLY = "monthly"
    ANNUAL = "annual"


@dataclass
class PaymentIntent:
    """Represents a payment intent (pre-payment)."""
    id: str
    organization_id: UUID
    amount_naira: int
    currency: str
    status: PaymentStatus
    tier: SKUTier
    intelligence_addon: Optional[IntelligenceAddon]
    billing_cycle: BillingCycle
    authorization_url: Optional[str]  # Paystack redirect URL
    access_code: Optional[str]  # Paystack access code
    reference: str  # Unique payment reference
    metadata: Dict[str, Any]
    created_at: datetime
    expires_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "organization_id": str(self.organization_id),
            "amount_naira": self.amount_naira,
            "amount_formatted": f"₦{self.amount_naira:,.0f}",
            "currency": self.currency,
            "status": self.status.value,
            "tier": self.tier.value,
            "intelligence_addon": self.intelligence_addon.value if self.intelligence_addon else None,
            "billing_cycle": self.billing_cycle.value,
            "authorization_url": self.authorization_url,
            "reference": self.reference,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }


@dataclass
class PaymentResult:
    """Result of a payment transaction."""
    success: bool
    reference: str
    status: PaymentStatus
    amount_naira: int
    message: str
    transaction_id: Optional[str] = None
    paid_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class SubscriptionInfo:
    """Information about a subscription."""
    organization_id: UUID
    tier: SKUTier
    intelligence_addon: Optional[IntelligenceAddon]
    billing_cycle: BillingCycle
    status: str  # active, trial, past_due, cancelled
    current_period_start: datetime
    current_period_end: datetime
    amount_naira: int
    is_trial: bool
    trial_ends_at: Optional[datetime]
    next_billing_date: Optional[datetime]
    payment_method: Optional[str]
    # Cancellation/downgrade fields
    cancel_at_period_end: bool = False
    cancellation_requested_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    scheduled_downgrade_tier: Optional[SKUTier] = None


# =============================================================================
# ABSTRACT PAYMENT PROVIDER
# =============================================================================

class PaymentProvider(ABC):
    """Abstract base class for payment providers."""
    
    @abstractmethod
    async def initialize_payment(
        self,
        email: str,
        amount_naira: int,
        reference: str,
        callback_url: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Initialize a payment transaction."""
        pass
    
    @abstractmethod
    async def verify_payment(self, reference: str) -> PaymentResult:
        """Verify a payment transaction."""
        pass
    
    @abstractmethod
    async def create_subscription(
        self,
        customer_email: str,
        plan_code: str,
        start_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Create a subscription plan."""
        pass
    
    @abstractmethod
    async def cancel_subscription(
        self,
        subscription_code: str,
        token: str,
    ) -> Dict[str, Any]:
        """Cancel a subscription."""
        pass
    
    @abstractmethod
    async def refund_payment(
        self,
        transaction_reference: str,
        amount_naira: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Refund a payment (full or partial)."""
        pass


# =============================================================================
# PAYSTACK PROVIDER (PRODUCTION IMPLEMENTATION)
# =============================================================================

class PaystackProvider(PaymentProvider):
    """
    Paystack payment provider for Nigerian Naira transactions.
    
    Production-ready implementation with:
    - Real API calls via httpx
    - Proper error handling
    - Retry logic for transient failures
    - Comprehensive logging
    
    Paystack API docs: https://paystack.com/docs/api/
    """
    
    def __init__(
        self,
        secret_key: Optional[str] = None,
        base_url: str = "https://api.paystack.co",
    ):
        from app.config import settings
        
        self.secret_key = secret_key or settings.paystack_secret_key
        self.base_url = base_url or settings.paystack_base_url
        
        # Validate we have credentials
        if not self.secret_key or self.secret_key == "":
            logger.warning("PaystackProvider initialized without secret key - using stub mode")
            self._is_stub = True
        else:
            self._is_stub = False
            logger.info(f"PaystackProvider initialized (live={self.secret_key.startswith('sk_live_')})")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for Paystack API requests."""
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to Paystack API with retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., /transaction/initialize)
            data: Request body for POST/PUT
            params: Query parameters for GET
            
        Returns:
            Parsed JSON response with error_code field
            
        Raises:
            PaystackAPIError: On API errors
        """
        import httpx
        from app.config import settings
        
        url = f"{self.base_url}{endpoint}"
        timeout = getattr(settings, 'paystack_timeout_seconds', 30)
        max_retries = getattr(settings, 'paystack_max_retries', 3)
        
        last_error = None
        
        # Retry loop with exponential backoff (#38)
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=float(timeout)) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=self._get_headers(),
                        json=data,
                        params=params,
                    )
                    
                    result = response.json()
                    
                    # Log the response (without sensitive data)
                    logger.debug(f"Paystack {method} {endpoint}: status={response.status_code}")
                    
                    if response.status_code >= 400:
                        error_code = self._map_http_error_code(response.status_code, result)
                        logger.error(f"Paystack API error [{error_code.value}]: {result.get('message', 'Unknown error')}")
                        return {
                            "status": False,
                            "error_code": error_code.value,
                            "error_name": error_code.name,
                            "message": result.get("message", f"HTTP {response.status_code}"),
                            "data": result.get("data"),
                        }
                    
                    # Success - add success code
                    result["error_code"] = BillingErrorCode.SUCCESS.value
                    return result
                    
            except httpx.TimeoutException:
                last_error = BillingErrorCode.TIMEOUT_ERROR
                logger.warning(f"Paystack API timeout (attempt {attempt + 1}/{max_retries}): {method} {endpoint}")
                if attempt < max_retries - 1:
                    import asyncio
                    backoff = (2 ** attempt) * 10  # 10s, 20s, 40s
                    logger.info(f"Retrying in {backoff} seconds...")
                    await asyncio.sleep(backoff)
                    continue
                    
            except httpx.ConnectError:
                last_error = BillingErrorCode.CONNECTION_REFUSED
                logger.warning(f"Paystack connection error (attempt {attempt + 1}/{max_retries}): {method} {endpoint}")
                if attempt < max_retries - 1:
                    import asyncio
                    backoff = (2 ** attempt) * 10
                    await asyncio.sleep(backoff)
                    continue
                    
            except httpx.RequestError as e:
                last_error = BillingErrorCode.NETWORK_ERROR
                logger.warning(f"Paystack request error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    import asyncio
                    backoff = (2 ** attempt) * 10
                    await asyncio.sleep(backoff)
                    continue
                    
            except Exception as e:
                last_error = BillingErrorCode.UNEXPECTED_ERROR
                logger.error(f"Paystack unexpected error: {e}")
                break  # Don't retry unexpected errors
        
        # All retries exhausted
        error_code = last_error or BillingErrorCode.NETWORK_ERROR
        logger.error(f"Paystack API failed after {max_retries} attempts [{error_code.value}]")
        return {
            "status": False,
            "error_code": error_code.value,
            "error_name": error_code.name,
            "message": get_error_message(error_code),
        }
    
    def _map_http_error_code(self, status_code: int, result: Dict[str, Any]) -> BillingErrorCode:
        """Map HTTP status code and response to BillingErrorCode."""
        message = result.get("message", "").lower()
        
        # Check for specific error messages from Paystack
        if "invalid" in message and "amount" in message:
            return BillingErrorCode.INVALID_AMOUNT
        if "declined" in message:
            return BillingErrorCode.CARD_DECLINED
        if "insufficient" in message:
            return BillingErrorCode.INSUFFICIENT_FUNDS
        if "expired" in message:
            return BillingErrorCode.EXPIRED_CARD
        if "duplicate" in message:
            return BillingErrorCode.DUPLICATE_TRANSACTION
        
        # Map by status code
        if status_code == 400:
            return BillingErrorCode.INVALID_AMOUNT
        elif status_code == 401:
            return BillingErrorCode.UNAUTHORIZED
        elif status_code == 404:
            return BillingErrorCode.TRANSACTION_NOT_FOUND
        elif status_code == 429:
            return BillingErrorCode.RATE_LIMITED
        elif status_code >= 500:
            return BillingErrorCode.PROVIDER_ERROR
        else:
            return BillingErrorCode.PAYMENT_FAILED
    
    async def initialize_payment(
        self,
        email: str,
        amount_naira: int,
        reference: str,
        callback_url: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Initialize a payment transaction with Paystack.
        
        API: POST https://api.paystack.co/transaction/initialize
        
        Args:
            email: Customer email
            amount_naira: Amount in Naira (will be converted to kobo)
            reference: Unique transaction reference
            callback_url: URL to redirect after payment
            metadata: Additional data to store with transaction
            
        Returns:
            Dict with status, message, data (authorization_url, access_code, reference)
        """
        if self._is_stub:
            logger.warning("PaystackProvider in STUB mode - returning fake data")
            return {
                "status": True,
                "message": "Authorization URL created (STUB MODE)",
                "data": {
                    "authorization_url": f"https://checkout.paystack.com/stub/{reference}",
                    "access_code": f"stub_access_{reference}",
                    "reference": reference,
                },
            }
        
        # Convert amount to kobo (100 kobo = 1 Naira)
        amount_kobo = amount_naira * 100
        
        payload = {
            "email": email,
            "amount": amount_kobo,
            "reference": reference,
            "callback_url": callback_url,
            "currency": "NGN",
            "channels": ["card", "bank", "ussd", "bank_transfer"],
        }
        
        if metadata:
            payload["metadata"] = metadata
        
        logger.info(f"Initializing Paystack payment: ref={reference}, amount=₦{amount_naira:,}")
        
        result = await self._make_request("POST", "/transaction/initialize", data=payload)
        
        if result.get("status"):
            logger.info(f"Payment initialized successfully: {reference}")
        else:
            logger.error(f"Payment initialization failed: {result.get('message')}")
        
        return result
    
    async def verify_payment(self, reference: str) -> PaymentResult:
        """
        Verify a payment transaction.
        
        API: GET https://api.paystack.co/transaction/verify/:reference
        
        Args:
            reference: Transaction reference to verify
            
        Returns:
            PaymentResult with success status and details
        """
        if self._is_stub:
            logger.warning("PaystackProvider in STUB mode - returning fake verification")
            return PaymentResult(
                success=True,
                reference=reference,
                status=PaymentStatus.SUCCESS,
                amount_naira=50000,
                message="Payment verified (STUB MODE)",
                transaction_id=f"stub_txn_{reference}",
                paid_at=datetime.utcnow(),
                metadata={"stub": True},
            )
        
        logger.info(f"Verifying Paystack payment: {reference}")
        
        result = await self._make_request("GET", f"/transaction/verify/{reference}")
        
        if not result.get("status"):
            return PaymentResult(
                success=False,
                reference=reference,
                status=PaymentStatus.FAILED,
                amount_naira=0,
                message=result.get("message", "Verification failed"),
            )
        
        data = result.get("data", {})
        tx_status = data.get("status", "").lower()
        
        # Map Paystack status to our status
        status_map = {
            "success": PaymentStatus.SUCCESS,
            "failed": PaymentStatus.FAILED,
            "pending": PaymentStatus.PENDING,
            "processing": PaymentStatus.PROCESSING,
            "abandoned": PaymentStatus.CANCELLED,
            "reversed": PaymentStatus.REFUNDED,
        }
        
        payment_status = status_map.get(tx_status, PaymentStatus.FAILED)
        success = payment_status == PaymentStatus.SUCCESS
        
        # Parse paid_at timestamp
        paid_at = None
        if data.get("paid_at"):
            try:
                paid_at = datetime.fromisoformat(data["paid_at"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass
        
        # Extract payment method details
        authorization = data.get("authorization", {})
        metadata_result = {
            "transaction_id": data.get("id"),
            "paystack_reference": data.get("reference"),
            "gateway_response": data.get("gateway_response"),
            "channel": data.get("channel"),
            "card_type": authorization.get("card_type"),
            "bank": authorization.get("bank"),
            "last4": authorization.get("last4"),
            "fees": data.get("fees"),
        }
        
        logger.info(f"Payment verification result: ref={reference}, status={tx_status}, success={success}")
        
        return PaymentResult(
            success=success,
            reference=reference,
            status=payment_status,
            amount_naira=data.get("amount", 0) // 100,  # Convert from kobo
            message=data.get("gateway_response", "Verified"),
            transaction_id=str(data.get("id", "")),
            paid_at=paid_at,
            metadata=metadata_result,
        )
    
    async def create_subscription(
        self,
        customer_email: str,
        plan_code: str,
        start_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Create a subscription for recurring payments.
        
        API: POST https://api.paystack.co/subscription
        
        Note: Requires customer to have a valid authorization (saved card).
        For Tekvwa, we use one-time payments for simplicity.
        """
        if self._is_stub:
            return {
                "status": True,
                "message": "Subscription created (STUB MODE)",
                "data": {
                    "subscription_code": f"stub_sub_{plan_code}",
                    "email_token": "stub_token",
                    "start_date": (start_date or datetime.utcnow()).isoformat(),
                },
            }
        
        payload = {
            "customer": customer_email,
            "plan": plan_code,
        }
        
        if start_date:
            payload["start_date"] = start_date.isoformat()
        
        logger.info(f"Creating Paystack subscription: {customer_email} -> {plan_code}")
        
        return await self._make_request("POST", "/subscription", data=payload)
    
    async def cancel_subscription(
        self,
        subscription_code: str,
        token: str,
    ) -> Dict[str, Any]:
        """
        Cancel/disable a subscription.
        
        API: POST https://api.paystack.co/subscription/disable
        """
        if self._is_stub:
            return {
                "status": True,
                "message": "Subscription cancelled (STUB MODE)",
            }
        
        payload = {
            "code": subscription_code,
            "token": token,
        }
        
        logger.info(f"Cancelling Paystack subscription: {subscription_code}")
        
        return await self._make_request("POST", "/subscription/disable", data=payload)
    
    async def refund_payment(
        self,
        transaction_reference: str,
        amount_naira: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Initiate a refund for a transaction.
        
        API: POST https://api.paystack.co/refund
        
        Args:
            transaction_reference: Reference of transaction to refund
            amount_naira: Amount to refund (None = full refund)
        """
        if self._is_stub:
            return {
                "status": True,
                "message": "Refund initiated (STUB MODE)",
                "data": {
                    "refund_id": f"stub_refund_{transaction_reference}",
                    "amount": amount_naira or 50000,
                },
            }
        
        payload = {
            "transaction": transaction_reference,
        }
        
        if amount_naira:
            payload["amount"] = amount_naira * 100  # Convert to kobo
        
        logger.info(f"Initiating Paystack refund: {transaction_reference}, amount={amount_naira}")
        
        return await self._make_request("POST", "/refund", data=payload)
    
    async def get_transaction(self, transaction_id: int) -> Dict[str, Any]:
        """
        Get details of a specific transaction by ID.
        
        API: GET https://api.paystack.co/transaction/:id
        """
        if self._is_stub:
            return {
                "status": True,
                "data": {
                    "id": transaction_id,
                    "status": "success",
                    "reference": f"stub_ref_{transaction_id}",
                },
            }
        
        return await self._make_request("GET", f"/transaction/{transaction_id}")
    
    async def list_transactions(
        self,
        page: int = 1,
        per_page: int = 50,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        List transactions on the account.
        
        API: GET https://api.paystack.co/transaction
        """
        if self._is_stub:
            return {
                "status": True,
                "data": [],
                "meta": {"total": 0, "page": page, "perPage": per_page},
            }
        
        params = {
            "page": page,
            "perPage": per_page,
        }
        
        if from_date:
            params["from"] = from_date.isoformat()
        if to_date:
            params["to"] = to_date.isoformat()
        
        return await self._make_request("GET", "/transaction", params=params)
    
    async def resolve_account(
        self,
        account_number: str,
        bank_code: str,
    ) -> Dict[str, Any]:
        """
        Resolve a bank account number to get account name.
        
        API: GET https://api.paystack.co/bank/resolve
        
        Useful for verifying customer bank details before refunds.
        """
        if self._is_stub:
            return {
                "status": True,
                "data": {
                    "account_number": account_number,
                    "account_name": "STUB ACCOUNT NAME",
                    "bank_id": 1,
                },
            }
        
        params = {
            "account_number": account_number,
            "bank_code": bank_code,
        }
        
        return await self._make_request("GET", "/bank/resolve", params=params)
    
    async def get_customer(
        self,
        customer_code: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get customer details including saved authorizations.
        
        API: GET https://api.paystack.co/customer/:customer_code
        
        Args:
            customer_code: Paystack customer code
            
        Returns:
            Customer data including authorizations or None
        """
        if self._is_stub:
            return {
                "id": 12345,
                "customer_code": customer_code,
                "email": "stub@example.com",
                "authorizations": [
                    {
                        "authorization_code": "AUTH_stub123",
                        "card_type": "visa",
                        "last4": "4081",
                        "exp_month": "12",
                        "exp_year": "2030",
                        "bank": "TEST BANK",
                        "channel": "card",
                        "reusable": True,
                    }
                ],
            }
        
        result = await self._make_request("GET", f"/customer/{customer_code}")
        
        if result.get("status"):
            return result.get("data")
        return None
    
    async def charge_authorization(
        self,
        authorization_code: str,
        email: str,
        amount_naira: int,
        reference: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PaymentResult:
        """
        Charge a saved authorization (card) for recurring/automatic payments.
        
        API: POST https://api.paystack.co/transaction/charge_authorization
        
        Args:
            authorization_code: Saved authorization code
            email: Customer email
            amount_naira: Amount to charge in Naira
            reference: Unique transaction reference
            metadata: Additional metadata
            
        Returns:
            PaymentResult with success/failure details
        """
        if self._is_stub:
            logger.warning("PaystackProvider in STUB mode - returning fake charge")
            return PaymentResult(
                success=True,
                reference=reference,
                status=PaymentStatus.SUCCESS,
                amount_naira=amount_naira,
                message="Charge successful (STUB MODE)",
                transaction_id=f"stub_charge_{reference}",
                paid_at=datetime.utcnow(),
                metadata={"stub": True},
            )
        
        amount_kobo = amount_naira * 100
        
        payload = {
            "authorization_code": authorization_code,
            "email": email,
            "amount": amount_kobo,
            "reference": reference,
            "currency": "NGN",
        }
        
        if metadata:
            payload["metadata"] = metadata
        
        logger.info(f"Charging authorization: ref={reference}, amount=₦{amount_naira:,}")
        
        result = await self._make_request("POST", "/transaction/charge_authorization", data=payload)
        
        if not result.get("status"):
            return PaymentResult(
                success=False,
                reference=reference,
                status=PaymentStatus.FAILED,
                amount_naira=amount_naira,
                message=result.get("message", "Charge failed"),
            )
        
        data = result.get("data", {})
        tx_status = data.get("status", "").lower()
        
        success = tx_status == "success"
        
        # Parse paid_at
        paid_at = None
        if data.get("paid_at"):
            try:
                paid_at = datetime.fromisoformat(data["paid_at"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                paid_at = datetime.utcnow() if success else None
        
        logger.info(f"Authorization charge result: ref={reference}, status={tx_status}, success={success}")
        
        return PaymentResult(
            success=success,
            reference=reference,
            status=PaymentStatus.SUCCESS if success else PaymentStatus.FAILED,
            amount_naira=data.get("amount", 0) // 100,
            message=data.get("gateway_response", "Charged"),
            transaction_id=str(data.get("id", "")),
            paid_at=paid_at,
            metadata={
                "transaction_id": data.get("id"),
                "gateway_response": data.get("gateway_response"),
                "channel": data.get("channel"),
            },
        )


# =============================================================================
# BILLING SERVICE
# =============================================================================

class BillingService:
    """
    Service for managing subscriptions and billing.
    
    Usage:
        service = BillingService(db)
        
        # Create payment intent for upgrade
        intent = await service.create_payment_intent(
            organization_id=org_id,
            tier=SKUTier.PROFESSIONAL,
            billing_cycle=BillingCycle.MONTHLY,
            admin_email="admin@company.com",
        )
        
        # Process webhook after payment
        await service.process_payment_webhook(payload)
        
        # Get subscription info
        info = await service.get_subscription_info(org_id)
    """
    
    def __init__(
        self,
        db: AsyncSession,
        payment_provider: Optional[PaymentProvider] = None,
    ):
        self.db = db
        self.payment_provider = payment_provider or PaystackProvider()
    
    # ===========================================
    # PRICING CALCULATION
    # ===========================================
    
    def calculate_subscription_price(
        self,
        tier: SKUTier,
        billing_cycle: BillingCycle,
        intelligence_addon: Optional[IntelligenceAddon] = None,
        additional_users: int = 0,
    ) -> int:
        """
        Calculate subscription price in Naira.
        
        Args:
            tier: SKU tier
            billing_cycle: Monthly or annual
            intelligence_addon: Optional intelligence add-on
            additional_users: Users beyond base tier limit
            
        Returns:
            Total price in Naira
        """
        tier_pricing = TIER_PRICING.get(tier)
        if not tier_pricing:
            raise ValueError(f"Unknown tier: {tier}")
        
        # Base price
        if billing_cycle == BillingCycle.ANNUAL:
            base_price = int(tier_pricing.annual_min)
        else:
            base_price = int(tier_pricing.monthly_min)
        
        # Additional users
        user_cost = additional_users * int(tier_pricing.price_per_additional_user)
        if billing_cycle == BillingCycle.ANNUAL:
            user_cost = user_cost * 10  # 10 months for annual (20% discount)
        
        # Intelligence add-on
        addon_cost = 0
        if intelligence_addon and intelligence_addon != IntelligenceAddon.NONE:
            addon_pricing = INTELLIGENCE_PRICING.get(intelligence_addon)
            if addon_pricing:
                addon_cost = int(addon_pricing.monthly_min)
                if billing_cycle == BillingCycle.ANNUAL:
                    addon_cost = addon_cost * 10  # Annual discount
        
        total = base_price + user_cost + addon_cost
        
        return total
    
    def calculate_prorated_upgrade_price(
        self,
        current_tier: SKUTier,
        new_tier: SKUTier,
        billing_cycle: BillingCycle,
        days_remaining: int,
        total_days_in_period: int,
        current_intelligence: Optional[IntelligenceAddon] = None,
        new_intelligence: Optional[IntelligenceAddon] = None,
    ) -> Dict[str, Any]:
        """
        Calculate prorated price for a mid-cycle upgrade.
        
        For upgrades: Customer pays the difference prorated for remaining days.
        
        Args:
            current_tier: Current SKU tier
            new_tier: Target SKU tier
            billing_cycle: Billing cycle (monthly/annual)
            days_remaining: Days left in current billing period
            total_days_in_period: Total days in the billing period (30 or 365)
            current_intelligence: Current intelligence addon
            new_intelligence: Target intelligence addon
            
        Returns:
            Dictionary with breakdown and prorated amount
        """
        # Get current subscription value
        current_price = self.calculate_subscription_price(
            tier=current_tier,
            billing_cycle=billing_cycle,
            intelligence_addon=current_intelligence,
        )
        
        # Get new subscription value
        new_price = self.calculate_subscription_price(
            tier=new_tier,
            billing_cycle=billing_cycle,
            intelligence_addon=new_intelligence,
        )
        
        # Calculate daily rate difference
        price_difference = new_price - current_price
        
        if price_difference <= 0:
            # This is a downgrade, not an upgrade
            return {
                "is_upgrade": False,
                "current_price": current_price,
                "new_price": new_price,
                "price_difference": price_difference,
                "prorated_amount": 0,
                "days_remaining": days_remaining,
                "total_days": total_days_in_period,
                "message": "Downgrades do not require payment. Changes apply at next billing cycle.",
            }
        
        # Calculate prorated amount
        # For monthly: daily_rate = monthly_price / 30
        # For annual: daily_rate = annual_price / 365
        daily_rate_difference = price_difference / total_days_in_period
        prorated_amount = int(daily_rate_difference * days_remaining)
        
        # Credit for unused current subscription
        current_daily_rate = current_price / total_days_in_period
        unused_credit = int(current_daily_rate * days_remaining)
        
        return {
            "is_upgrade": True,
            "current_tier": current_tier.value,
            "new_tier": new_tier.value,
            "billing_cycle": billing_cycle.value,
            "current_price": current_price,
            "new_price": new_price,
            "price_difference": price_difference,
            "days_remaining": days_remaining,
            "total_days": total_days_in_period,
            "unused_credit": unused_credit,
            "prorated_charge": prorated_amount,
            "prorated_amount": prorated_amount,  # Amount to charge now
            "prorated_amount_formatted": f"₦{prorated_amount:,}",
            "new_period_amount": new_price,  # Full amount for next billing cycle
            "message": f"Pay ₦{prorated_amount:,} now for the remaining {days_remaining} days, then ₦{new_price:,}/{billing_cycle.value}",
        }
    
    async def calculate_upgrade_proration(
        self,
        organization_id: UUID,
        new_tier: SKUTier,
        new_intelligence: Optional[IntelligenceAddon] = None,
    ) -> Dict[str, Any]:
        """
        Calculate prorated upgrade price for an organization.
        
        This fetches the current subscription details and calculates
        the prorated amount for upgrading to a new tier.
        """
        # Get current subscription
        result = await self.db.execute(
            select(TenantSKU).where(
                and_(
                    TenantSKU.organization_id == organization_id,
                    TenantSKU.is_active == True,
                )
            )
        )
        tenant_sku = result.scalar_one_or_none()
        
        if not tenant_sku:
            return {
                "error": "No active subscription found",
                "is_upgrade": None,
            }
        
        # Calculate days remaining
        now = datetime.utcnow()
        billing_cycle = BillingCycle(tenant_sku.billing_cycle)
        
        if tenant_sku.current_period_end:
            period_end = tenant_sku.current_period_end
            if isinstance(period_end, date) and not isinstance(period_end, datetime):
                period_end = datetime.combine(period_end, datetime.min.time())
            days_remaining = max(0, (period_end - now).days)
        else:
            days_remaining = 30 if billing_cycle == BillingCycle.MONTHLY else 365
        
        total_days = 30 if billing_cycle == BillingCycle.MONTHLY else 365
        
        return self.calculate_prorated_upgrade_price(
            current_tier=tenant_sku.tier,
            new_tier=new_tier,
            billing_cycle=billing_cycle,
            days_remaining=days_remaining,
            total_days_in_period=total_days,
            current_intelligence=tenant_sku.intelligence_addon,
            new_intelligence=new_intelligence,
        )
    
    async def validate_downgrade(
        self,
        organization_id: UUID,
        target_tier: SKUTier,
    ) -> Dict[str, Any]:
        """
        Validate if a downgrade is possible by checking current usage against target tier limits.
        
        Args:
            organization_id: Organization attempting to downgrade
            target_tier: Target tier to downgrade to
            
        Returns:
            Dictionary with validation result and any exceeded limits
        """
        from app.services.metering_service import MeteringService
        from app.models.sku import TIER_LIMITS, UsageMetricType
        
        metering = MeteringService(self.db)
        
        # Get current usage
        current_usage = await metering.get_all_current_usage(organization_id)
        
        # Get target tier limits
        target_limits = TIER_LIMITS.get(target_tier, {})
        
        exceeded_metrics = []
        warnings = []
        
        # Map metric names to limit keys
        metric_limit_map = {
            "transactions": "transactions_per_month",
            "users": "users",
            "entities": "entities",
            "invoices": "invoices_per_month",
            "api_calls": "api_calls_per_month",
            "ocr_pages": "ocr_pages_per_month",
            "storage_mb": "storage_mb",
            "ml_inferences": "ml_inferences_per_month",
            "employees": "employees",
        }
        
        display_names = {
            "transactions": "Monthly Transactions",
            "users": "Active Users",
            "entities": "Business Entities",
            "invoices": "Monthly Invoices",
            "api_calls": "API Calls",
            "ocr_pages": "OCR Pages",
            "storage_mb": "Storage (MB)",
            "ml_inferences": "ML Inferences",
            "employees": "Employees",
        }
        
        for metric_name, usage in current_usage.items():
            limit_key = metric_limit_map.get(metric_name)
            if not limit_key:
                continue
            
            limit = target_limits.get(limit_key, -1)
            
            # -1 means unlimited
            if limit == -1:
                continue
            
            if usage > limit:
                exceeded_metrics.append({
                    "metric": metric_name,
                    "display_name": display_names.get(metric_name, metric_name),
                    "current_usage": usage,
                    "target_limit": limit,
                    "excess": usage - limit,
                    "action_required": f"Reduce {display_names.get(metric_name, metric_name)} from {usage:,} to {limit:,} or fewer",
                })
            elif usage > limit * 0.8:
                # Warn if close to limit after downgrade
                warnings.append({
                    "metric": metric_name,
                    "display_name": display_names.get(metric_name, metric_name),
                    "current_usage": usage,
                    "target_limit": limit,
                    "percentage": (usage / limit) * 100,
                })
        
        can_downgrade = len(exceeded_metrics) == 0
        
        return {
            "can_downgrade": can_downgrade,
            "target_tier": target_tier.value,
            "exceeded_limits": exceeded_metrics if exceeded_metrics else None,
            "warnings": warnings if warnings else None,
            "message": (
                "You can proceed with the downgrade."
                if can_downgrade
                else f"Cannot downgrade: {len(exceeded_metrics)} usage metric(s) exceed the target tier limits. Please reduce usage first."
            ),
            "error_code": BillingErrorCode.SUCCESS.value if can_downgrade else BillingErrorCode.DOWNGRADE_NOT_ALLOWED.value,
        }
    
    async def request_downgrade(
        self,
        organization_id: UUID,
        target_tier: SKUTier,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Request a downgrade to a lower tier.
        
        Downgrades take effect at the end of the current billing period.
        If force=True, will schedule even if limits exceeded (with warning).
        
        Args:
            organization_id: Organization requesting downgrade
            target_tier: Target tier to downgrade to
            force: If True, schedule downgrade even with exceeded limits
            
        Returns:
            Dictionary with downgrade request result
        """
        # Validate downgrade
        validation = await self.validate_downgrade(organization_id, target_tier)
        
        if not validation["can_downgrade"] and not force:
            return {
                "success": False,
                "message": validation["message"],
                "exceeded_limits": validation["exceeded_limits"],
                "error_code": BillingErrorCode.DOWNGRADE_NOT_ALLOWED.value,
            }
        
        # Get current subscription
        result = await self.db.execute(
            select(TenantSKU).where(
                and_(
                    TenantSKU.organization_id == organization_id,
                    TenantSKU.is_active == True,
                )
            )
        )
        tenant_sku = result.scalar_one_or_none()
        
        if not tenant_sku:
            return {
                "success": False,
                "message": "No active subscription found",
                "error_code": BillingErrorCode.SUBSCRIPTION_NOT_FOUND.value,
            }
        
        # Check tier hierarchy
        tier_order = {SKUTier.CORE: 0, SKUTier.PROFESSIONAL: 1, SKUTier.ENTERPRISE: 2}
        if tier_order.get(target_tier, 0) >= tier_order.get(tenant_sku.tier, 0):
            return {
                "success": False,
                "message": f"Target tier ({target_tier.value}) is not lower than current tier ({tenant_sku.tier.value})",
                "error_code": BillingErrorCode.INVALID_PLAN_CHANGE.value,
            }
        
        now = datetime.utcnow()
        previous_tier = tenant_sku.tier.value
        
        # Schedule downgrade at period end
        tenant_sku.cancel_at_period_end = True
        tenant_sku.cancellation_requested_at = now
        tenant_sku.cancellation_reason = f"Downgrade to {target_tier.value} requested"
        tenant_sku.scheduled_downgrade_tier = target_tier
        tenant_sku.notes = f"Scheduled downgrade from {previous_tier} to {target_tier.value}. Effective: {tenant_sku.current_period_end.strftime('%Y-%m-%d') if tenant_sku.current_period_end else 'end of period'}."
        
        await self.db.flush()
        
        # Send confirmation email
        await self._send_downgrade_scheduled_email(
            organization_id=organization_id,
            previous_tier=previous_tier,
            target_tier=target_tier.value,
            effective_date=tenant_sku.current_period_end,
            exceeded_limits=validation.get("exceeded_limits"),
        )
        
        return {
            "success": True,
            "message": f"Downgrade to {target_tier.value} scheduled for end of billing period",
            "current_tier": previous_tier,
            "target_tier": target_tier.value,
            "effective_date": tenant_sku.current_period_end.isoformat() if tenant_sku.current_period_end else None,
            "exceeded_limits": validation.get("exceeded_limits"),
            "warnings": validation.get("warnings"),
            "error_code": BillingErrorCode.SUCCESS.value,
        }
    
    async def _send_downgrade_scheduled_email(
        self,
        organization_id: UUID,
        previous_tier: str,
        target_tier: str,
        effective_date: Optional[datetime],
        exceeded_limits: Optional[List[Dict]] = None,
    ) -> None:
        """Send downgrade scheduled confirmation email."""
        from app.services.billing_email_service import BillingEmailService
        from app.models.organization import Organization
        from app.models.user import User
        
        try:
            org_result = await self.db.execute(
                select(Organization).where(Organization.id == organization_id)
            )
            org = org_result.scalar_one_or_none()
            
            admin_result = await self.db.execute(
                select(User)
                .where(User.organization_id == organization_id)
                .where(User.is_active == True)
                .order_by(User.created_at)
                .limit(1)
            )
            admin_user = admin_result.scalar_one_or_none()
            
            if admin_user and admin_user.email and org:
                billing_email_service = BillingEmailService(self.db)
                await billing_email_service.send_scheduled_cancellation(
                    email=admin_user.email,
                    organization_name=org.name,
                    tier=previous_tier,
                    effective_date=effective_date,
                )
        except Exception as e:
            logger.error(f"Failed to send downgrade scheduled email: {e}")
    
    def get_tier_pricing_display(
        self,
        tier: SKUTier,
    ) -> Dict[str, Any]:
        """Get pricing display information for a tier."""
        pricing = TIER_PRICING.get(tier)
        if not pricing:
            return {}
        
        return {
            "tier": tier.value,
            "name": pricing.name,
            "tagline": pricing.tagline,
            "monthly": {
                "amount": int(pricing.monthly_min),
                "formatted": f"₦{int(pricing.monthly_min):,}",
            },
            "annual": {
                "amount": int(pricing.annual_min),
                "formatted": f"₦{int(pricing.annual_min):,}",
                "monthly_equivalent": f"₦{int(pricing.annual_min) // 12:,}",
                "savings": f"₦{int(pricing.monthly_min) * 12 - int(pricing.annual_min):,}",
            },
            "base_users": pricing.base_users_included,
            "per_user": {
                "amount": int(pricing.price_per_additional_user),
                "formatted": f"₦{int(pricing.price_per_additional_user):,}",
            },
        }
    
    # ===========================================
    # PAYMENT INTENTS
    # ===========================================
    
    async def validate_trial_to_paid_conversion(
        self,
        organization_id: UUID,
    ) -> Dict[str, Any]:
        """
        Validate that an organization can convert from trial to paid.
        
        This checks:
        1. Organization has an active trial
        2. Organization has a valid payment method on file (Paystack authorization)
        3. Trial hasn't already ended
        
        Args:
            organization_id: Organization to validate
            
        Returns:
            Dictionary with validation result and any issues
        """
        result = await self.db.execute(
            select(TenantSKU).where(
                and_(
                    TenantSKU.organization_id == organization_id,
                    TenantSKU.is_active == True,
                )
            )
        )
        tenant_sku = result.scalar_one_or_none()
        
        if not tenant_sku:
            return {
                "can_convert": False,
                "reason": "no_subscription",
                "message": "No active subscription found for this organization.",
            }
        
        now = datetime.utcnow()
        
        # Check if currently on trial
        if not tenant_sku.trial_ends_at:
            return {
                "can_convert": False,
                "reason": "not_on_trial",
                "message": "Organization is not currently on a trial.",
                "current_tier": tenant_sku.tier.value,
            }
        
        if tenant_sku.trial_ends_at < now:
            return {
                "can_convert": False,
                "reason": "trial_expired",
                "message": "Trial has already expired. Please start a new subscription.",
                "trial_ended_at": tenant_sku.trial_ends_at.isoformat(),
            }
        
        # Check for saved payment method (Paystack authorization)
        has_payment_method = False
        payment_method_details = None
        
        metadata = tenant_sku.custom_metadata or {}
        paystack_sub = metadata.get("paystack_subscription", {})
        
        if paystack_sub.get("customer_code"):
            # Customer has been registered with Paystack
            # Check if they have a saved authorization
            try:
                customer_code = paystack_sub["customer_code"]
                customer_info = await self.payment_provider.get_customer(customer_code)
                
                if customer_info and customer_info.get("authorizations"):
                    authorizations = customer_info["authorizations"]
                    # Find valid authorization
                    for auth in authorizations:
                        if auth.get("reusable", False):
                            has_payment_method = True
                            payment_method_details = {
                                "type": auth.get("channel", "card"),
                                "card_type": auth.get("card_type"),
                                "last4": auth.get("last4"),
                                "exp_month": auth.get("exp_month"),
                                "exp_year": auth.get("exp_year"),
                                "bank": auth.get("bank"),
                            }
                            break
            except Exception as e:
                logger.warning(f"Error checking customer payment methods: {e}")
        
        # Check for pending payment transaction that could provide authorization
        payment_result = await self.db.execute(
            select(PaymentTransaction)
            .where(PaymentTransaction.organization_id == organization_id)
            .where(PaymentTransaction.status == "success")
            .order_by(PaymentTransaction.created_at.desc())
            .limit(1)
        )
        last_payment = payment_result.scalar_one_or_none()
        
        if last_payment and last_payment.card_last4:
            has_payment_method = True
            payment_method_details = {
                "type": last_payment.payment_method or "card",
                "card_type": last_payment.card_type,
                "last4": last_payment.card_last4,
                "bank": last_payment.card_bank,
            }
        
        if not has_payment_method:
            return {
                "can_convert": False,
                "reason": "no_payment_method",
                "message": "No valid payment method on file. Please add a payment method to continue.",
                "action_required": "add_payment_method",
            }
        
        # Calculate days remaining in trial
        days_remaining = (tenant_sku.trial_ends_at - now).days
        
        return {
            "can_convert": True,
            "reason": "valid",
            "message": "Organization can convert from trial to paid subscription.",
            "trial_ends_at": tenant_sku.trial_ends_at.isoformat(),
            "days_remaining": days_remaining,
            "current_tier": tenant_sku.tier.value,
            "payment_method": payment_method_details,
        }
    
    async def convert_trial_to_paid(
        self,
        organization_id: UUID,
        tier: Optional[SKUTier] = None,
        billing_cycle: Optional[BillingCycle] = None,
    ) -> Dict[str, Any]:
        """
        Convert a trial subscription to a paid subscription.
        
        Args:
            organization_id: Organization to convert
            tier: Target tier (defaults to current trial tier)
            billing_cycle: Billing cycle (defaults to monthly)
            
        Returns:
            Dictionary with conversion result
        """
        # First validate
        validation = await self.validate_trial_to_paid_conversion(organization_id)
        
        if not validation.get("can_convert"):
            return {
                "success": False,
                "message": validation.get("message"),
                "reason": validation.get("reason"),
                "action_required": validation.get("action_required"),
            }
        
        # Get current subscription
        result = await self.db.execute(
            select(TenantSKU).where(
                and_(
                    TenantSKU.organization_id == organization_id,
                    TenantSKU.is_active == True,
                )
            )
        )
        tenant_sku = result.scalar_one_or_none()
        
        if not tenant_sku:
            return {"success": False, "message": "No subscription found"}
        
        # Use current tier if not specified
        target_tier = tier or tenant_sku.tier
        target_cycle = billing_cycle or BillingCycle.MONTHLY
        
        now = datetime.utcnow()
        
        # Calculate price
        amount = self.calculate_subscription_price(
            tier=target_tier,
            billing_cycle=target_cycle,
            intelligence_addon=tenant_sku.intelligence_addon,
        )
        
        # Try to charge using saved payment method
        metadata = tenant_sku.custom_metadata or {}
        paystack_sub = metadata.get("paystack_subscription", {})
        
        if paystack_sub.get("customer_code"):
            try:
                # Attempt to charge with saved authorization
                charge_result = await self.payment_provider.charge_authorization(
                    authorization_code=paystack_sub.get("authorization_code"),
                    email=paystack_sub.get("customer_email"),
                    amount_naira=amount,
                    reference=f"TVP-CONV-{organization_id.hex[:8]}-{now.strftime('%Y%m%d%H%M%S')}",
                    metadata={
                        "organization_id": str(organization_id),
                        "tier": target_tier.value,
                        "billing_cycle": target_cycle.value,
                        "conversion_type": "trial_to_paid",
                    },
                )
                
                if charge_result.success:
                    # Update subscription
                    tenant_sku.trial_ends_at = None
                    tenant_sku.current_period_start = now
                    
                    if target_cycle == BillingCycle.ANNUAL:
                        tenant_sku.current_period_end = now + timedelta(days=365)
                    else:
                        tenant_sku.current_period_end = now + timedelta(days=30)
                    
                    tenant_sku.tier = target_tier
                    tenant_sku.billing_cycle = target_cycle.value
                    
                    await self.db.flush()
                    
                    # Send confirmation
                    await self._send_trial_conversion_success_email(
                        organization_id=organization_id,
                        tier=target_tier.value,
                        amount=amount,
                        reference=charge_result.reference,
                    )
                    
                    return {
                        "success": True,
                        "message": "Successfully converted to paid subscription",
                        "tier": target_tier.value,
                        "billing_cycle": target_cycle.value,
                        "amount_charged": amount,
                        "next_billing_date": tenant_sku.current_period_end.isoformat(),
                    }
                else:
                    return {
                        "success": False,
                        "message": f"Payment failed: {charge_result.message}",
                        "reason": "payment_failed",
                        "action_required": "update_payment_method",
                    }
                    
            except Exception as e:
                logger.error(f"Error charging for trial conversion: {e}")
                return {
                    "success": False,
                    "message": "Payment processing error. Please try again or update your payment method.",
                    "reason": "payment_error",
                    "error": str(e),
                }
        else:
            # No saved authorization - need to redirect to payment page
            return {
                "success": False,
                "message": "No saved payment method. Please complete checkout.",
                "reason": "no_authorization",
                "action_required": "complete_checkout",
                "checkout_url": f"/billing/upgrade?tier={target_tier.value}&cycle={target_cycle.value}",
            }
    
    async def _send_trial_conversion_success_email(
        self,
        organization_id: UUID,
        tier: str,
        amount: int,
        reference: str,
    ) -> None:
        """Send email confirming successful trial to paid conversion."""
        from app.services.billing_email_service import BillingEmailService
        from app.models.organization import Organization
        from app.models.user import User
        
        try:
            org_result = await self.db.execute(
                select(Organization).where(Organization.id == organization_id)
            )
            org = org_result.scalar_one_or_none()
            
            admin_result = await self.db.execute(
                select(User)
                .where(User.organization_id == organization_id)
                .where(User.is_active == True)
                .order_by(User.created_at)
                .limit(1)
            )
            admin_user = admin_result.scalar_one_or_none()
            
            if admin_user and admin_user.email and org:
                billing_email_service = BillingEmailService(self.db)
                
                result = await self.db.execute(
                    select(TenantSKU).where(TenantSKU.organization_id == organization_id)
                )
                tenant_sku = result.scalar_one_or_none()
                
                await billing_email_service.send_payment_success(
                    email=admin_user.email,
                    organization_name=org.name,
                    tier=tier,
                    amount_naira=amount,
                    reference=reference,
                    payment_date=datetime.utcnow(),
                    next_billing_date=tenant_sku.current_period_end if tenant_sku else None,
                )
        except Exception as e:
            logger.error(f"Failed to send trial conversion email: {e}")
    
    async def create_payment_intent(
        self,
        organization_id: UUID,
        tier: SKUTier,
        billing_cycle: BillingCycle,
        admin_email: str,
        intelligence_addon: Optional[IntelligenceAddon] = None,
        additional_users: int = 0,
        callback_url: Optional[str] = None,
        user_id: Optional[UUID] = None,
        is_upgrade: bool = False,
        apply_proration: bool = True,
        discount_percent: int = 0,  # Billing feature #34
        currency: str = "NGN",  # Billing feature #36
    ) -> PaymentIntent:
        """
        Create a payment intent for subscription upgrade/purchase.
        
        This initializes a payment with Paystack and returns
        the authorization URL for the customer to complete payment.
        Also creates a PaymentTransaction record in the database.
        
        Args:
            organization_id: Organization making the payment
            tier: Target SKU tier
            billing_cycle: Monthly or annual
            admin_email: Email for Paystack
            intelligence_addon: Optional intelligence tier
            additional_users: Extra user seats
            callback_url: URL to redirect after payment
            user_id: User initiating the payment
            is_upgrade: If True, calculate prorated amount for mid-cycle upgrade
            apply_proration: If True and is_upgrade, apply prorated pricing
            discount_percent: Discount percentage to apply (0-100) (#34)
            currency: Payment currency (NGN, USD, EUR, GBP) (#36)
        """
        import uuid as uuid_module
        
        # Calculate price - check if this is a mid-cycle upgrade
        if is_upgrade and apply_proration:
            proration_result = await self.calculate_upgrade_proration(
                organization_id=organization_id,
                new_tier=tier,
                new_intelligence=intelligence_addon,
            )
            
            if proration_result.get("is_upgrade") and proration_result.get("prorated_amount", 0) > 0:
                # Use prorated amount for mid-cycle upgrade
                amount = proration_result["prorated_amount"]
                is_prorated = True
            else:
                # Fall back to full price
                amount = self.calculate_subscription_price(
                    tier=tier,
                    billing_cycle=billing_cycle,
                    intelligence_addon=intelligence_addon,
                    additional_users=additional_users,
                )
                is_prorated = False
        else:
            # Standard full price calculation
            amount = self.calculate_subscription_price(
                tier=tier,
                billing_cycle=billing_cycle,
                intelligence_addon=intelligence_addon,
                additional_users=additional_users,
            )
            is_prorated = False
        
        # Apply discount if provided (#34: Discount codes)
        discount_amount = 0
        if discount_percent > 0 and discount_percent <= 100:
            discount_amount = int(amount * discount_percent / 100)
            amount = amount - discount_amount
            logger.info(f"Applied {discount_percent}% discount: -{discount_amount} NGN, new amount: {amount}")
        
        # =====================================================================
        # AMOUNT VALIDATION (#39: Validate amount against SKU config)
        # =====================================================================
        if amount < MIN_PAYMENT_AMOUNT:
            logger.error(f"Payment amount {amount} below minimum {MIN_PAYMENT_AMOUNT}")
            raise ValueError(
                f"Payment amount ₦{amount:,} is below minimum allowed ₦{MIN_PAYMENT_AMOUNT:,}. "
                f"Error code: {BillingErrorCode.AMOUNT_TOO_LOW.value}"
            )
        
        if amount > MAX_PAYMENT_AMOUNT:
            logger.error(f"Payment amount {amount} exceeds maximum {MAX_PAYMENT_AMOUNT}")
            raise ValueError(
                f"Payment amount ₦{amount:,} exceeds maximum allowed ₦{MAX_PAYMENT_AMOUNT:,}. "
                f"Error code: {BillingErrorCode.AMOUNT_TOO_HIGH.value}"
            )
        
        # Validate against expected SKU pricing to prevent charging wrong amount
        expected_base_price = self.calculate_subscription_price(
            tier=tier,
            billing_cycle=billing_cycle,
            intelligence_addon=intelligence_addon,
            additional_users=additional_users,
        )
        
        # Allow for prorated amounts and discounts, but amount should not exceed base price
        if not is_prorated and discount_percent == 0 and amount != expected_base_price:
            logger.error(f"Amount mismatch: calculated={amount}, expected={expected_base_price}")
            raise ValueError(
                f"Amount validation failed: calculated amount doesn't match SKU pricing. "
                f"Error code: {BillingErrorCode.INVALID_AMOUNT.value}"
            )
        
        logger.info(f"Amount validated: {amount} NGN for {tier.value} ({billing_cycle.value})")
        # =====================================================================
        
        # Handle multi-currency (#36: Multi-currency checkout)
        # Paystack accepts NGN, so we store both original and converted amounts
        original_amount_ngn = amount
        display_currency = currency.upper() if currency else "NGN"
        
        # Generate unique reference
        reference = f"TVP-{organization_id.hex[:8]}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        # Metadata for webhook processing
        metadata = {
            "organization_id": str(organization_id),
            "tier": tier.value,
            "billing_cycle": billing_cycle.value,
            "intelligence_addon": intelligence_addon.value if intelligence_addon else None,
            "additional_users": additional_users,
            "is_upgrade": is_upgrade,
            "is_prorated": is_prorated,
            "discount_percent": discount_percent,
            "discount_amount": discount_amount,
            "display_currency": display_currency,
        }
        
        # Initialize payment with provider
        result = await self.payment_provider.initialize_payment(
            email=admin_email,
            amount_naira=amount,
            reference=reference,
            callback_url=callback_url or f"/billing/callback?ref={reference}",
            metadata=metadata,
        )
        
        if not result.get("status"):
            raise ValueError(f"Payment initialization failed: {result.get('message')}")
        
        data = result.get("data", {})
        
        # Create PaymentTransaction record in database
        # Note: tier and intelligence_addon columns are VARCHAR, so pass string values
        payment_transaction = PaymentTransaction(
            organization_id=organization_id,
            user_id=user_id,
            reference=reference,
            paystack_reference=data.get("reference"),
            paystack_access_code=data.get("access_code"),
            authorization_url=data.get("authorization_url"),
            transaction_type="payment",
            status="pending",
            amount_kobo=amount * 100,  # Convert to kobo
            currency="NGN",
            tier=tier.value if tier else None,  # Convert enum to string
            billing_cycle=billing_cycle.value,
            intelligence_addon=intelligence_addon.value if intelligence_addon else None,  # Convert enum to string
            additional_users=additional_users,
            custom_metadata={**metadata, "email": admin_email, "callback_url": callback_url},
        )
        self.db.add(payment_transaction)
        await self.db.flush()  # Get the ID without committing
        
        logger.info(f"Created payment transaction {payment_transaction.id} for ref={reference}")
        
        return PaymentIntent(
            id=str(payment_transaction.id),
            organization_id=organization_id,
            amount_naira=amount,
            currency="NGN",
            status=PaymentStatus.PENDING,
            tier=tier,
            intelligence_addon=intelligence_addon,
            billing_cycle=billing_cycle,
            authorization_url=data.get("authorization_url"),
            access_code=data.get("access_code"),
            reference=reference,
            metadata=metadata,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
    
    async def verify_and_process_payment(
        self,
        reference: str,
    ) -> PaymentResult:
        """
        Verify a payment and update subscription if successful.
        
        This is typically called after customer completes payment
        on Paystack checkout page. Updates the PaymentTransaction record.
        
        Includes amount validation (#39) to cross-check verified amount
        against the expected amount stored in PaymentTransaction.
        """
        # Look up existing transaction record
        tx_result = await self.db.execute(
            select(PaymentTransaction).where(PaymentTransaction.reference == reference)
        )
        payment_tx = tx_result.scalar_one_or_none()
        
        # Verify with provider
        result = await self.payment_provider.verify_payment(reference)
        
        if not result.success:
            logger.warning(f"Payment verification failed for {reference}: {result.message}")
            
            # Update transaction record if exists
            if payment_tx:
                payment_tx.status = "failed"
                payment_tx.failed_at = datetime.utcnow()
                payment_tx.error_message = result.message
                payment_tx.gateway_response = result.message
                payment_tx.error_code = BillingErrorCode.PAYMENT_FAILED.value
                if result.metadata:
                    payment_tx.paystack_response = result.metadata
            
            return result
        
        # =====================================================================
        # AMOUNT VALIDATION (#39: Cross-check verified amount against expected)
        # =====================================================================
        if payment_tx:
            expected_amount_kobo = payment_tx.amount_kobo
            verified_amount_kobo = result.amount_naira * 100 if result.amount_naira else 0
            
            # Allow small variance (e.g., rounding differences) but catch major mismatches
            amount_difference = abs(verified_amount_kobo - expected_amount_kobo)
            max_allowed_difference = 100  # 1 Naira tolerance for rounding
            
            if amount_difference > max_allowed_difference:
                logger.error(
                    f"Amount mismatch for {reference}: "
                    f"expected={expected_amount_kobo} kobo, "
                    f"verified={verified_amount_kobo} kobo, "
                    f"difference={amount_difference} kobo"
                )
                
                payment_tx.status = "failed"
                payment_tx.failed_at = datetime.utcnow()
                payment_tx.error_message = f"Amount mismatch: expected {expected_amount_kobo}, got {verified_amount_kobo}"
                payment_tx.error_code = BillingErrorCode.INVALID_AMOUNT.value
                
                return PaymentResult(
                    success=False,
                    reference=reference,
                    status=PaymentStatus.FAILED,
                    amount_naira=result.amount_naira,
                    message=f"Amount verification failed. Error code: {BillingErrorCode.INVALID_AMOUNT.value}",
                )
            
            logger.info(f"Amount verified for {reference}: {verified_amount_kobo} kobo matches expected")
        # =====================================================================
        
        # Update transaction record with success details
        if payment_tx:
            payment_tx.status = "success"
            payment_tx.paid_at = result.paid_at or datetime.utcnow()
            payment_tx.verified_at = datetime.utcnow()
            payment_tx.gateway_response = result.message
            payment_tx.error_code = BillingErrorCode.SUCCESS.value

            if result.metadata:
                payment_tx.paystack_response = result.metadata
                payment_tx.payment_method = result.metadata.get("channel")
                payment_tx.card_type = result.metadata.get("card_type")
                payment_tx.card_last4 = result.metadata.get("last4")
                payment_tx.card_bank = result.metadata.get("bank")
                if result.metadata.get("fees"):
                    payment_tx.fee_kobo = result.metadata["fees"]
            
            logger.info(f"Updated payment transaction {payment_tx.id}: status=success")
        
        logger.info(f"Payment verified successfully for {reference}")
        
        return result
    
    # ===========================================
    # WEBHOOK HANDLING
    # ===========================================
    
    async def process_payment_webhook(
        self,
        event_type: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Process Paystack webhook events.
        
        Events handled:
        - charge.success: Payment completed
        - subscription.create: New subscription
        - subscription.disable: Subscription cancelled
        - invoice.create: New Paystack invoice generated
        - invoice.update: Invoice status changed
        - invoice.payment_failed: Payment failed
        - transfer.success: Refund/payout completed
        - transfer.failed: Refund/payout failed
        - refund.processed: Refund completed
        
        Webhook setup: https://dashboard.paystack.com/#/settings/webhooks
        """
        logger.info(f"Processing webhook: {event_type}")
        
        # IDEMPOTENCY CHECK (#45) - Prevent duplicate webhook processing
        data = payload.get("data", {})
        event_id = data.get("id")
        if event_id:
            existing_tx = await self.db.execute(
                select(PaymentTransaction).where(
                    PaymentTransaction.webhook_event_id == str(event_id)
                )
            )
            if existing_tx.scalar_one_or_none():
                logger.info(f"Duplicate webhook ignored (idempotency): event_id={event_id}")
                return {
                    "handled": False,
                    "reason": "duplicate",
                    "event_id": str(event_id),
                    "error_code": BillingErrorCode.DUPLICATE_WEBHOOK.value,
                    "message": BILLING_ERROR_MESSAGES[BillingErrorCode.DUPLICATE_WEBHOOK],
                }
        
        if event_type == "charge.success":
            return await self._handle_charge_success(payload)
        elif event_type == "subscription.create":
            return await self._handle_subscription_created(payload)
        elif event_type == "subscription.disable":
            return await self._handle_subscription_cancelled(payload)
        elif event_type == "invoice.create":
            return await self._handle_invoice_created(payload)
        elif event_type == "invoice.update":
            return await self._handle_invoice_updated(payload)
        elif event_type == "invoice.payment_failed":
            return await self._handle_payment_failed(payload)
        elif event_type == "transfer.success":
            return await self._handle_transfer_success(payload)
        elif event_type == "transfer.failed":
            return await self._handle_transfer_failed(payload)
        elif event_type == "refund.processed":
            return await self._handle_refund_processed(payload)
        else:
            logger.debug(f"Unhandled webhook event: {event_type}")
            return {"handled": False, "event": event_type}
    
    async def _handle_charge_success(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle successful charge webhook."""
        data = payload.get("data", {})
        reference = data.get("reference")
        metadata = data.get("metadata", {})
        authorization = data.get("authorization", {})
        
        # Update PaymentTransaction record
        tx_result = await self.db.execute(
            select(PaymentTransaction).where(PaymentTransaction.reference == reference)
        )
        payment_tx = tx_result.scalar_one_or_none()
        
        if payment_tx:
            payment_tx.status = "success"
            payment_tx.paid_at = datetime.utcnow()
            payment_tx.verified_at = datetime.utcnow()
            payment_tx.webhook_received_at = datetime.utcnow()
            payment_tx.webhook_event_id = str(data.get("id", ""))
            payment_tx.gateway_response = data.get("gateway_response")
            payment_tx.paystack_response = data
            payment_tx.payment_method = data.get("channel")
            payment_tx.card_type = authorization.get("card_type")
            payment_tx.card_last4 = authorization.get("last4")
            payment_tx.card_bank = authorization.get("bank")
            if data.get("fees"):
                payment_tx.fee_kobo = data["fees"]
            
            logger.info(f"Updated payment transaction {payment_tx.id} via webhook: status=success")
        
        organization_id_str = metadata.get("organization_id")
        if not organization_id_str:
            logger.error(f"No organization_id in charge webhook: {reference}")
            return {"handled": False, "error": "Missing organization_id"}
        
        try:
            org_id = UUID(organization_id_str)
            tier = SKUTier(metadata.get("tier", "core"))
            billing_cycle = metadata.get("billing_cycle", "monthly")
            intelligence_addon_str = metadata.get("intelligence_addon")
            intelligence_addon = IntelligenceAddon(intelligence_addon_str) if intelligence_addon_str else None
            
            # Update TenantSKU
            await self._upgrade_tenant_sku(
                organization_id=org_id,
                tier=tier,
                billing_cycle=billing_cycle,
                intelligence_addon=intelligence_addon,
            )
            
            return {
                "handled": True,
                "organization_id": organization_id_str,
                "tier": tier.value,
                "reference": reference,
            }
        except Exception as e:
            logger.error(f"Error processing charge success: {e}")
            return {"handled": False, "error": str(e)}
    
    async def _handle_subscription_created(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handle subscription created webhook.
        
        This is triggered when a customer subscribes to a plan via Paystack.
        Updates TenantSKU with subscription details.
        """
        data = payload.get("data", {})
        customer = data.get("customer", {})
        plan = data.get("plan", {})
        
        subscription_code = data.get("subscription_code")
        email_token = data.get("email_token")
        customer_email = customer.get("email")
        plan_code = plan.get("plan_code")
        
        logger.info(f"Processing subscription.create webhook: {subscription_code}")
        
        # Extract organization ID from metadata or customer email
        metadata = data.get("metadata", {})
        organization_id_str = metadata.get("organization_id")
        
        if not organization_id_str:
            # Try to find organization by customer email
            from app.models.user import User
            from app.models.organization import Organization
            
            user_result = await self.db.execute(
                select(User).where(User.email == customer_email)
            )
            user = user_result.scalar_one_or_none()
            
            if user and user.organization_id:
                organization_id_str = str(user.organization_id)
            else:
                logger.warning(f"Could not find organization for subscription: {subscription_code}")
                return {"handled": False, "error": "Organization not found"}
        
        try:
            org_id = UUID(organization_id_str)
            
            # Determine tier from plan code or metadata
            tier_str = metadata.get("tier")
            if not tier_str and plan_code:
                # Extract tier from plan code (e.g., "pro_audit_professional_monthly")
                if "professional" in plan_code.lower():
                    tier_str = "professional"
                elif "enterprise" in plan_code.lower():
                    tier_str = "enterprise"
                else:
                    tier_str = "core"
            
            tier = SKUTier(tier_str) if tier_str else SKUTier.CORE
            
            # Get billing cycle from plan
            billing_cycle = "monthly"
            if plan.get("interval") == "annually":
                billing_cycle = "annual"
            
            # Update TenantSKU with subscription details
            result = await self.db.execute(
                select(TenantSKU).where(
                    and_(
                        TenantSKU.organization_id == org_id,
                        TenantSKU.is_active == True,
                    )
                )
            )
            tenant_sku = result.scalar_one_or_none()
            
            now = datetime.utcnow()
            
            if tenant_sku:
                # Update existing SKU
                tenant_sku.tier = tier
                tenant_sku.billing_cycle = billing_cycle
                tenant_sku.trial_ends_at = None  # No longer on trial
                tenant_sku.current_period_start = now
                
                # Set period end based on billing cycle
                if billing_cycle == "annual":
                    tenant_sku.current_period_end = now + timedelta(days=365)
                else:
                    tenant_sku.current_period_end = now + timedelta(days=30)
                
                # Store subscription details in metadata
                metadata_update = tenant_sku.custom_metadata or {}
                metadata_update["paystack_subscription"] = {
                    "subscription_code": subscription_code,
                    "email_token": email_token,
                    "plan_code": plan_code,
                    "customer_code": customer.get("customer_code"),
                    "created_at": now.isoformat(),
                }
                tenant_sku.custom_metadata = metadata_update
                
                # Clear any dunning status
                if "dunning" in metadata_update:
                    del metadata_update["dunning"]
                    tenant_sku.custom_metadata = metadata_update
                
            else:
                # Create new SKU
                tenant_sku = TenantSKU(
                    organization_id=org_id,
                    tier=tier,
                    billing_cycle=billing_cycle,
                    is_active=True,
                    trial_ends_at=None,
                    current_period_start=now,
                    current_period_end=now + timedelta(days=30 if billing_cycle == "monthly" else 365),
                    custom_metadata={
                        "paystack_subscription": {
                            "subscription_code": subscription_code,
                            "email_token": email_token,
                            "plan_code": plan_code,
                            "customer_code": customer.get("customer_code"),
                            "created_at": now.isoformat(),
                        }
                    },
                )
                self.db.add(tenant_sku)
            
            await self.db.flush()
            
            # Send confirmation email
            from app.services.billing_email_service import BillingEmailService
            from app.models.organization import Organization
            
            org_result = await self.db.execute(
                select(Organization).where(Organization.id == org_id)
            )
            org = org_result.scalar_one_or_none()
            
            if customer_email and org:
                billing_email_service = BillingEmailService(self.db)
                amount = self.calculate_subscription_price(
                    tier=tier,
                    billing_cycle=BillingCycle(billing_cycle),
                )
                await billing_email_service.send_payment_success(
                    email=customer_email,
                    organization_name=org.name,
                    tier=tier.value,
                    amount_naira=amount,
                    reference=subscription_code,
                    payment_date=now,
                    next_billing_date=tenant_sku.current_period_end,
                )
            
            logger.info(f"Subscription created for org {org_id}: {tier.value}")
            
            return {
                "handled": True,
                "event": "subscription.create",
                "organization_id": organization_id_str,
                "tier": tier.value,
                "subscription_code": subscription_code,
            }
            
        except Exception as e:
            logger.error(f"Error processing subscription.create: {e}")
            return {"handled": False, "error": str(e)}
    
    async def _handle_subscription_cancelled(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handle subscription cancelled/disabled webhook.
        
        This is triggered when a subscription is cancelled.
        Handles end-of-period access and downgrade logic.
        """
        data = payload.get("data", {})
        subscription_code = data.get("subscription_code")
        customer = data.get("customer", {})
        
        logger.info(f"Processing subscription.disable webhook: {subscription_code}")
        
        # Find TenantSKU by subscription code in metadata
        from app.models.organization import Organization
        from app.models.user import User
        
        result = await self.db.execute(
            select(TenantSKU).where(TenantSKU.is_active == True)
        )
        tenant_skus = result.scalars().all()
        
        target_sku = None
        for sku in tenant_skus:
            subscription_data = (sku.custom_metadata or {}).get("paystack_subscription", {})
            if subscription_data.get("subscription_code") == subscription_code:
                target_sku = sku
                break
        
        if not target_sku:
            # Try finding by customer email
            customer_email = customer.get("email")
            if customer_email:
                user_result = await self.db.execute(
                    select(User).where(User.email == customer_email)
                )
                user = user_result.scalar_one_or_none()
                
                if user and user.organization_id:
                    sku_result = await self.db.execute(
                        select(TenantSKU).where(TenantSKU.organization_id == user.organization_id)
                    )
                    target_sku = sku_result.scalar_one_or_none()
        
        if not target_sku:
            logger.warning(f"Could not find SKU for cancelled subscription: {subscription_code}")
            return {"handled": False, "error": "Subscription not found"}
        
        now = datetime.utcnow()
        org_id = target_sku.organization_id
        previous_tier = target_sku.tier.value
        
        # Mark subscription as cancelled but allow access until period end
        metadata = target_sku.custom_metadata or {}
        metadata["subscription_cancelled"] = {
            "cancelled_at": now.isoformat(),
            "previous_tier": previous_tier,
            "reason": data.get("status", "cancelled"),
            "access_until": target_sku.current_period_end.isoformat() if target_sku.current_period_end else now.isoformat(),
        }
        
        # Remove active subscription data
        if "paystack_subscription" in metadata:
            metadata["previous_subscription"] = metadata.pop("paystack_subscription")
        
        target_sku.custom_metadata = metadata
        target_sku.notes = f"Subscription cancelled on {now.strftime('%Y-%m-%d')}. Access until {target_sku.current_period_end.strftime('%Y-%m-%d') if target_sku.current_period_end else 'now'}."
        
        # If past period end, immediately downgrade
        if target_sku.current_period_end and target_sku.current_period_end <= now:
            target_sku.tier = SKUTier.CORE
            target_sku.intelligence_addon = None
            logger.info(f"Immediately downgraded org {org_id} to Core (period ended)")
        
        await self.db.flush()
        
        # Send cancellation confirmation email
        from app.services.billing_email_service import BillingEmailService
        
        org_result = await self.db.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org = org_result.scalar_one_or_none()
        
        admin_result = await self.db.execute(
            select(User)
            .where(User.organization_id == org_id)
            .where(User.is_active == True)
            .order_by(User.created_at)
            .limit(1)
        )
        admin_user = admin_result.scalar_one_or_none()
        
        if admin_user and admin_user.email and org:
            billing_email_service = BillingEmailService(self.db)
            # Use trial_ended_downgrade as a proxy for cancellation notification
            await billing_email_service.send_trial_ended_downgrade(
                email=admin_user.email,
                organization_name=org.name,
                previous_tier=previous_tier,
            )
        
        logger.info(f"Subscription cancelled for org {org_id}: {subscription_code}")
        
        return {
            "handled": True,
            "event": "subscription.disable",
            "organization_id": str(org_id),
            "previous_tier": previous_tier,
            "subscription_code": subscription_code,
        }
    
    async def _handle_payment_failed(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle payment failed webhook."""
        data = payload.get("data", {})
        reference = data.get("reference")
        metadata = data.get("metadata", {})
        
        # Update PaymentTransaction record
        tx_result = await self.db.execute(
            select(PaymentTransaction).where(PaymentTransaction.reference == reference)
        )
        payment_tx = tx_result.scalar_one_or_none()
        
        if payment_tx:
            payment_tx.status = "failed"
            payment_tx.failed_at = datetime.utcnow()
            payment_tx.webhook_received_at = datetime.utcnow()
            payment_tx.webhook_event_id = str(data.get("id", ""))
            payment_tx.gateway_response = data.get("gateway_response")
            payment_tx.error_message = data.get("message", "Payment failed")
            payment_tx.paystack_response = data
            
            logger.info(f"Updated payment transaction {payment_tx.id} via webhook: status=failed")
        
        # Get organization and admin for notification
        organization_id_str = metadata.get("organization_id")
        if organization_id_str:
            try:
                from app.models.organization import Organization
                from app.models.user import User
                from app.services.billing_email_service import BillingEmailService
                from app.services.dunning_service import DunningService
                
                org_id = UUID(organization_id_str)
                
                # Get organization
                org_result = await self.db.execute(
                    select(Organization).where(Organization.id == org_id)
                )
                org = org_result.scalar_one_or_none()
                
                # Get admin user
                admin_result = await self.db.execute(
                    select(User)
                    .where(User.organization_id == org_id)
                    .where(User.is_active == True)
                    .order_by(User.created_at)
                    .limit(1)
                )
                admin_user = admin_result.scalar_one_or_none()
                
                # Calculate amount from transaction or kobo value
                amount_naira = payment_tx.amount_kobo // 100 if payment_tx else data.get("amount", 0) // 100
                failure_reason = data.get("message", "Payment failed")
                
                # Record failure in dunning system
                dunning_service = DunningService(self.db)
                await dunning_service.record_payment_failure(
                    organization_id=org_id,
                    reason=failure_reason,
                    amount_naira=amount_naira,
                    transaction_reference=reference,
                )
                
                # Send notification email
                if admin_user and admin_user.email and org:
                    billing_email_service = BillingEmailService(self.db)
                    await billing_email_service.send_payment_failed(
                        email=admin_user.email,
                        organization_name=org.name,
                        amount_naira=amount_naira,
                        reason=failure_reason,
                        retry_url="/checkout",
                    )
                    logger.info(f"Sent payment failure notification to {admin_user.email}")
                
            except Exception as e:
                logger.error(f"Error handling payment failure notification: {e}")
        
        return {"handled": True, "event": "invoice.payment_failed", "reference": reference}
    
    async def _handle_invoice_created(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handle Paystack invoice.create webhook.
        
        This is triggered when Paystack generates a new invoice for subscription billing.
        Tracks the invoice for reconciliation and sends notification.
        """
        data = payload.get("data", {})
        invoice_id = data.get("invoice_code") or data.get("id")
        subscription = data.get("subscription", {})
        customer = data.get("customer", {})
        
        logger.info(f"Processing invoice.create webhook: {invoice_id}")
        
        amount_kobo = data.get("amount", 0)
        due_date_str = data.get("due_date")
        description = data.get("description", "Subscription payment")
        customer_email = customer.get("email")
        subscription_code = subscription.get("subscription_code") if isinstance(subscription, dict) else subscription
        
        # Find organization by subscription code or customer email
        organization_id = None
        org_name = None
        
        from app.models.organization import Organization
        from app.models.user import User
        
        # Try to find by subscription code in TenantSKU metadata
        if subscription_code:
            result = await self.db.execute(
                select(TenantSKU).where(TenantSKU.is_active == True)
            )
            for sku in result.scalars().all():
                sub_data = (sku.custom_metadata or {}).get("paystack_subscription", {})
                if sub_data.get("subscription_code") == subscription_code:
                    organization_id = sku.organization_id
                    break
        
        # Fallback to customer email
        if not organization_id and customer_email:
            user_result = await self.db.execute(
                select(User).where(User.email == customer_email)
            )
            user = user_result.scalar_one_or_none()
            if user and user.organization_id:
                organization_id = user.organization_id
        
        if organization_id:
            # Get organization name
            org_result = await self.db.execute(
                select(Organization).where(Organization.id == organization_id)
            )
            org = org_result.scalar_one_or_none()
            org_name = org.name if org else "Customer"
            
            # Create or update PaymentTransaction to track this invoice
            tx_reference = f"INV-{invoice_id}"
            
            # Check if transaction already exists
            existing_result = await self.db.execute(
                select(PaymentTransaction).where(PaymentTransaction.reference == tx_reference)
            )
            existing_tx = existing_result.scalar_one_or_none()
            
            if not existing_tx:
                # Create new transaction record for tracking
                payment_tx = PaymentTransaction(
                    organization_id=organization_id,
                    reference=tx_reference,
                    paystack_reference=str(invoice_id),
                    transaction_type="subscription",
                    status="pending",
                    amount_kobo=amount_kobo,
                    currency="NGN",
                    paystack_invoice_id=str(invoice_id),
                    paystack_invoice_status="pending",
                    webhook_received_at=datetime.utcnow(),
                    paystack_response=data,
                    custom_metadata={
                        "subscription_code": subscription_code,
                        "description": description,
                    },
                )
                self.db.add(payment_tx)
                await self.db.flush()
                logger.info(f"Created payment transaction for invoice {invoice_id}")
            
            # Send invoice notification email
            if customer_email and org_name:
                from app.services.billing_email_service import BillingEmailService
                
                billing_email = BillingEmailService(self.db)
                due_date = datetime.fromisoformat(due_date_str.replace("Z", "+00:00")) if due_date_str else datetime.utcnow()
                
                await billing_email.send_paystack_invoice_notification(
                    email=customer_email,
                    organization_name=org_name,
                    invoice_id=str(invoice_id),
                    amount_naira=amount_kobo // 100,
                    due_date=due_date,
                    description=description,
                )
                logger.info(f"Sent invoice notification to {customer_email}")
        
        return {
            "handled": True,
            "event": "invoice.create",
            "invoice_id": invoice_id,
            "organization_id": str(organization_id) if organization_id else None,
        }
    
    async def _handle_invoice_updated(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handle Paystack invoice.update webhook.
        
        Syncs invoice status changes (pending, paid, failed, etc.) from Paystack.
        """
        data = payload.get("data", {})
        invoice_id = data.get("invoice_code") or data.get("id")
        invoice_status = data.get("status", "").lower()
        paid_at_str = data.get("paid_at")
        
        logger.info(f"Processing invoice.update webhook: {invoice_id}, status={invoice_status}")
        
        # Find the PaymentTransaction by invoice ID
        tx_reference = f"INV-{invoice_id}"
        result = await self.db.execute(
            select(PaymentTransaction).where(
                or_(
                    PaymentTransaction.reference == tx_reference,
                    PaymentTransaction.paystack_invoice_id == str(invoice_id),
                )
            )
        )
        payment_tx = result.scalar_one_or_none()
        
        if payment_tx:
            # Update invoice status
            payment_tx.paystack_invoice_status = invoice_status
            payment_tx.webhook_received_at = datetime.utcnow()
            
            # Map Paystack invoice status to our transaction status
            if invoice_status == "paid" or invoice_status == "success":
                payment_tx.status = "success"
                if paid_at_str:
                    try:
                        payment_tx.paid_at = datetime.fromisoformat(paid_at_str.replace("Z", "+00:00"))
                    except:
                        payment_tx.paid_at = datetime.utcnow()
                else:
                    payment_tx.paid_at = datetime.utcnow()
            elif invoice_status == "failed":
                payment_tx.status = "failed"
                payment_tx.error_message = data.get("message", "Invoice payment failed")
            elif invoice_status == "cancelled":
                payment_tx.status = "cancelled"
            
            # Store full response
            existing_response = payment_tx.paystack_response or {}
            existing_response["invoice_update"] = data
            payment_tx.paystack_response = existing_response
            
            logger.info(f"Updated payment transaction {payment_tx.id}: status={payment_tx.status}")
        else:
            logger.warning(f"No payment transaction found for invoice {invoice_id}")
        
        return {
            "handled": True,
            "event": "invoice.update",
            "invoice_id": invoice_id,
            "status": invoice_status,
        }
    
    async def _handle_transfer_success(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handle Paystack transfer.success webhook.
        
        This confirms that a refund or payout has been completed successfully.
        Updates the original transaction and notifies the customer.
        """
        data = payload.get("data", {})
        transfer_code = data.get("transfer_code")
        reference = data.get("reference")
        reason = data.get("reason", "")
        amount_kobo = data.get("amount", 0)
        recipient = data.get("recipient", {})
        
        logger.info(f"Processing transfer.success webhook: {transfer_code}, ref={reference}")
        
        # Check if this is a refund by looking at the reason or reference
        is_refund = "refund" in reason.lower() if reason else False
        
        # Try to find the original payment transaction
        # Refund references often contain the original reference
        original_reference = None
        if reference and reference.startswith("REF-"):
            # Our refund references format: REF-{original_reference}
            original_reference = reference.replace("REF-", "")
        
        # Look for transaction by refund reference in metadata
        payment_tx = None
        if original_reference:
            result = await self.db.execute(
                select(PaymentTransaction).where(PaymentTransaction.reference == original_reference)
            )
            payment_tx = result.scalar_one_or_none()
        
        # Also try to find by transfer_code in metadata
        if not payment_tx:
            result = await self.db.execute(
                select(PaymentTransaction).where(
                    PaymentTransaction.refund_reference == transfer_code
                )
            )
            payment_tx = result.scalar_one_or_none()
        
        if payment_tx:
            # Update transaction with refund completion
            payment_tx.status = "refunded"
            payment_tx.refunded_at = datetime.utcnow()
            payment_tx.refund_amount_kobo = amount_kobo
            payment_tx.refund_reference = transfer_code
            
            # Store transfer details
            existing_response = payment_tx.paystack_response or {}
            existing_response["transfer_success"] = data
            payment_tx.paystack_response = existing_response
            
            logger.info(f"Updated transaction {payment_tx.id} with refund completion")
            
            # Send refund confirmation email
            from app.models.organization import Organization
            from app.models.user import User
            from app.services.billing_email_service import BillingEmailService
            
            org_result = await self.db.execute(
                select(Organization).where(Organization.id == payment_tx.organization_id)
            )
            org = org_result.scalar_one_or_none()
            
            # Get admin user for email
            admin_result = await self.db.execute(
                select(User)
                .where(User.organization_id == payment_tx.organization_id)
                .where(User.is_active == True)
                .order_by(User.created_at)
                .limit(1)
            )
            admin_user = admin_result.scalar_one_or_none()
            
            if admin_user and admin_user.email and org:
                billing_email = BillingEmailService(self.db)
                await billing_email.send_refund_processed(
                    email=admin_user.email,
                    organization_name=org.name,
                    amount_naira=amount_kobo // 100,
                    original_reference=payment_tx.reference,
                    refund_reference=transfer_code,
                    reason=reason if reason else payment_tx.refund_reason,
                )
                logger.info(f"Sent refund confirmation to {admin_user.email}")
        else:
            logger.warning(f"No original transaction found for transfer {transfer_code}")
        
        return {
            "handled": True,
            "event": "transfer.success",
            "transfer_code": transfer_code,
            "amount_kobo": amount_kobo,
        }
    
    async def _handle_transfer_failed(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handle Paystack transfer.failed webhook.
        
        This indicates a refund or payout has failed.
        Notifies the customer and admin for manual resolution.
        """
        data = payload.get("data", {})
        transfer_code = data.get("transfer_code")
        reference = data.get("reference")
        reason = data.get("reason", "")
        amount_kobo = data.get("amount", 0)
        failure_reason = data.get("message") or data.get("gateway_response") or "Transfer failed"
        
        logger.info(f"Processing transfer.failed webhook: {transfer_code}, reason={failure_reason}")
        
        # Try to find the original payment transaction
        original_reference = None
        if reference and reference.startswith("REF-"):
            original_reference = reference.replace("REF-", "")
        
        payment_tx = None
        if original_reference:
            result = await self.db.execute(
                select(PaymentTransaction).where(PaymentTransaction.reference == original_reference)
            )
            payment_tx = result.scalar_one_or_none()
        
        if not payment_tx:
            result = await self.db.execute(
                select(PaymentTransaction).where(
                    PaymentTransaction.refund_reference == transfer_code
                )
            )
            payment_tx = result.scalar_one_or_none()
        
        if payment_tx:
            # Update transaction with failure info (but don't mark as refunded)
            payment_tx.error_message = f"Refund failed: {failure_reason}"
            payment_tx.refund_reference = transfer_code
            
            # Store transfer failure details
            existing_response = payment_tx.paystack_response or {}
            existing_response["transfer_failed"] = data
            payment_tx.paystack_response = existing_response
            
            logger.info(f"Updated transaction {payment_tx.id} with refund failure")
            
            # Send failure notification
            from app.models.organization import Organization
            from app.models.user import User
            from app.services.billing_email_service import BillingEmailService
            
            org_result = await self.db.execute(
                select(Organization).where(Organization.id == payment_tx.organization_id)
            )
            org = org_result.scalar_one_or_none()
            
            admin_result = await self.db.execute(
                select(User)
                .where(User.organization_id == payment_tx.organization_id)
                .where(User.is_active == True)
                .order_by(User.created_at)
                .limit(1)
            )
            admin_user = admin_result.scalar_one_or_none()
            
            if admin_user and admin_user.email and org:
                billing_email = BillingEmailService(self.db)
                await billing_email.send_refund_failed(
                    email=admin_user.email,
                    organization_name=org.name,
                    amount_naira=amount_kobo // 100,
                    original_reference=payment_tx.reference,
                    failure_reason=failure_reason,
                )
                logger.info(f"Sent refund failure notification to {admin_user.email}")
        else:
            logger.warning(f"No original transaction found for failed transfer {transfer_code}")
        
        return {
            "handled": True,
            "event": "transfer.failed",
            "transfer_code": transfer_code,
            "failure_reason": failure_reason,
        }
    
    async def _handle_refund_processed(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handle Paystack refund.processed webhook.
        
        This is the primary refund completion event from Paystack.
        Updates the transaction status and sends confirmation.
        """
        data = payload.get("data", {})
        refund_id = data.get("id")
        transaction_reference = data.get("transaction_reference")
        amount_kobo = data.get("amount", 0)
        status = data.get("status", "").lower()
        merchant_note = data.get("merchant_note", "")
        customer_note = data.get("customer_note", "")
        
        logger.info(f"Processing refund.processed webhook: refund_id={refund_id}, tx_ref={transaction_reference}")
        
        # Find the original payment transaction by Paystack reference
        payment_tx = None
        if transaction_reference:
            result = await self.db.execute(
                select(PaymentTransaction).where(
                    or_(
                        PaymentTransaction.paystack_reference == transaction_reference,
                        PaymentTransaction.reference == transaction_reference,
                    )
                )
            )
            payment_tx = result.scalar_one_or_none()
        
        if payment_tx:
            now = datetime.utcnow()
            
            # Update transaction with refund details
            if status == "processed" or status == "success":
                payment_tx.status = "refunded"
                payment_tx.refunded_at = now
            elif status == "failed":
                payment_tx.status = "failed"
                payment_tx.error_message = f"Refund failed: {merchant_note or customer_note}"
            
            payment_tx.refund_amount_kobo = amount_kobo
            payment_tx.refund_reference = str(refund_id)
            payment_tx.refund_reason = merchant_note or customer_note
            
            # Store refund details
            existing_response = payment_tx.paystack_response or {}
            existing_response["refund_processed"] = data
            payment_tx.paystack_response = existing_response
            
            logger.info(f"Updated transaction {payment_tx.id} with refund: status={payment_tx.status}")
            
            # Send refund confirmation if successful
            if status == "processed" or status == "success":
                from app.models.organization import Organization
                from app.models.user import User
                from app.services.billing_email_service import BillingEmailService
                
                org_result = await self.db.execute(
                    select(Organization).where(Organization.id == payment_tx.organization_id)
                )
                org = org_result.scalar_one_or_none()
                
                admin_result = await self.db.execute(
                    select(User)
                    .where(User.organization_id == payment_tx.organization_id)
                    .where(User.is_active == True)
                    .order_by(User.created_at)
                    .limit(1)
                )
                admin_user = admin_result.scalar_one_or_none()
                
                if admin_user and admin_user.email and org:
                    billing_email = BillingEmailService(self.db)
                    await billing_email.send_refund_processed(
                        email=admin_user.email,
                        organization_name=org.name,
                        amount_naira=amount_kobo // 100,
                        original_reference=payment_tx.reference,
                        refund_reference=str(refund_id),
                        reason=merchant_note or customer_note,
                    )
                    logger.info(f"Sent refund confirmation to {admin_user.email}")
        else:
            logger.warning(f"No transaction found for refund {refund_id}, tx_ref={transaction_reference}")
        
        return {
            "handled": True,
            "event": "refund.processed",
            "refund_id": refund_id,
            "transaction_reference": transaction_reference,
            "status": status,
        }
    
    # ===========================================
    # SUBSCRIPTION MANAGEMENT
    # ===========================================
    
    async def _upgrade_tenant_sku(
        self,
        organization_id: UUID,
        tier: SKUTier,
        billing_cycle: str,
        intelligence_addon: Optional[IntelligenceAddon] = None,
    ) -> None:
        """Upgrade a tenant's SKU after successful payment."""
        result = await self.db.execute(
            select(TenantSKU).where(
                and_(
                    TenantSKU.organization_id == organization_id,
                    TenantSKU.is_active == True,
                )
            )
        )
        tenant_sku = result.scalar_one_or_none()
        
        if tenant_sku:
            # Update existing
            tenant_sku.tier = tier
            tenant_sku.billing_cycle = billing_cycle
            tenant_sku.intelligence_addon = intelligence_addon
            tenant_sku.trial_ends_at = None  # No longer trial
            tenant_sku.current_period_start = datetime.utcnow()
            
            # Set period end based on billing cycle
            if billing_cycle == "annual":
                tenant_sku.current_period_end = datetime.utcnow() + timedelta(days=365)
            else:
                tenant_sku.current_period_end = datetime.utcnow() + timedelta(days=30)
        else:
            # Create new
            from app.config.sku_config import TIER_PRICING
            pricing = TIER_PRICING.get(tier)
            base_price = int(pricing.monthly_min) if pricing else 50000
            
            tenant_sku = TenantSKU(
                organization_id=organization_id,
                tier=tier,
                billing_cycle=billing_cycle,
                intelligence_addon=intelligence_addon,
                is_active=True,
                trial_ends_at=None,
                current_period_start=datetime.utcnow(),
                current_period_end=datetime.utcnow() + timedelta(days=30 if billing_cycle == "monthly" else 365),
                base_price_naira=base_price,
            )
            self.db.add(tenant_sku)
        
        await self.db.flush()
        logger.info(f"Upgraded organization {organization_id} to {tier.value}")
    
    async def get_subscription_info(
        self,
        organization_id: UUID,
    ) -> Optional[SubscriptionInfo]:
        """Get subscription information for an organization."""
        result = await self.db.execute(
            select(TenantSKU).where(
                and_(
                    TenantSKU.organization_id == organization_id,
                    TenantSKU.is_active == True,
                )
            )
        )
        tenant_sku = result.scalar_one_or_none()
        
        if not tenant_sku:
            return None
        
        # Determine status with grace period logic
        now = datetime.utcnow()
        status = self._determine_subscription_status(tenant_sku, now)
        
        # Calculate amount
        amount = self.calculate_subscription_price(
            tier=tenant_sku.tier,
            billing_cycle=BillingCycle(tenant_sku.billing_cycle),
            intelligence_addon=tenant_sku.intelligence_addon,
        )
        
        return SubscriptionInfo(
            organization_id=organization_id,
            tier=tenant_sku.tier,
            intelligence_addon=tenant_sku.intelligence_addon,
            billing_cycle=BillingCycle(tenant_sku.billing_cycle),
            status=status,
            current_period_start=tenant_sku.current_period_start,
            current_period_end=tenant_sku.current_period_end,
            amount_naira=amount,
            is_trial=tenant_sku.is_trial,
            trial_ends_at=tenant_sku.trial_ends_at,
            next_billing_date=tenant_sku.current_period_end,
            payment_method=None,  # Would come from Paystack customer data
            # Cancellation/downgrade fields
            cancel_at_period_end=tenant_sku.cancel_at_period_end or False,
            cancellation_requested_at=tenant_sku.cancellation_requested_at,
            cancellation_reason=tenant_sku.cancellation_reason,
            scheduled_downgrade_tier=tenant_sku.scheduled_downgrade_tier,
        )
    
    def _determine_subscription_status(
        self,
        tenant_sku: TenantSKU,
        now: Optional[datetime] = None,
    ) -> str:
        """
        Determine subscription status with grace period logic.
        
        Status flow:
        - trial: In trial period
        - active: Paid and current
        - past_due: Period ended but within grace period
        - suspended: Grace period expired, account suspended
        - cancelled: User cancelled subscription
        
        Grace period configuration:
        - 7 days after period end before marking as past_due
        - 21 days total before suspension
        """
        from app.config.sku_config import SKUTier
        
        if now is None:
            now = datetime.utcnow()
        
        # Check for suspension
        if tenant_sku.suspended_at:
            return "suspended"
        
        # Check if cancelled (cancel_at_period_end flag is set)
        if tenant_sku.cancel_at_period_end and tenant_sku.cancellation_requested_at:
            return "cancelled"
        
        # Check for trial - handle timezone-aware vs naive comparison
        if tenant_sku.trial_ends_at:
            trial_ends = tenant_sku.trial_ends_at
            # Make both datetimes naive for comparison if needed
            if trial_ends.tzinfo is not None:
                trial_ends = trial_ends.replace(tzinfo=None)
            if tenant_sku.trial_ends_at.tzinfo is not None and now.tzinfo is None:
                now = now.replace(tzinfo=None)
            
            if trial_ends > now:
                return "trial"
            else:
                # Trial expired - check grace period (3 days)
                trial_grace_days = 3
                grace_end = trial_ends + timedelta(days=trial_grace_days)
                if now < grace_end:
                    return "trial_expired"
                # After trial grace, should be downgraded
                return "trial_ended"
        
        # Check period end with grace period
        if tenant_sku.current_period_end:
            period_end = tenant_sku.current_period_end
            if isinstance(period_end, date) and not isinstance(period_end, datetime):
                period_end = datetime.combine(period_end, datetime.min.time())
            
            if now < period_end:
                return "active"
            
            # Past period end - check grace period
            # Grace period: 7 days soft (past_due), 21 days hard (suspended)
            soft_grace_days = 7
            hard_grace_days = 21
            
            days_past_due = (now - period_end).days
            
            if days_past_due <= soft_grace_days:
                return "grace_period"
            elif days_past_due <= hard_grace_days:
                return "past_due"
            else:
                return "suspended"
        
        # Default to active if no period set
        return "active"
    
    async def check_subscription_access(
        self,
        organization_id: UUID,
    ) -> Dict[str, Any]:
        """
        Check if organization has valid subscription access.
        
        Returns dict with:
        - has_access: bool
        - status: subscription status
        - tier: current tier
        - message: human-readable status message
        - days_remaining: days until access expires (if applicable)
        - grace_period_remaining: days remaining in grace period (if applicable)
        """
        result = await self.db.execute(
            select(TenantSKU).where(
                and_(
                    TenantSKU.organization_id == organization_id,
                )
            )
        )
        tenant_sku = result.scalar_one_or_none()
        
        if not tenant_sku:
            return {
                "has_access": False,
                "status": "no_subscription",
                "tier": None,
                "message": "No subscription found. Please subscribe to continue.",
                "days_remaining": 0,
            }
        
        now = datetime.utcnow()
        status = self._determine_subscription_status(tenant_sku, now)
        
        access_granted_statuses = ["active", "trial", "grace_period", "trial_expired"]
        has_access = status in access_granted_statuses and tenant_sku.is_active
        
        # Calculate days remaining
        days_remaining = 0
        grace_period_remaining = 0
        
        if tenant_sku.trial_ends_at and tenant_sku.trial_ends_at > now:
            days_remaining = (tenant_sku.trial_ends_at - now).days
        elif tenant_sku.current_period_end:
            period_end = tenant_sku.current_period_end
            if isinstance(period_end, date) and not isinstance(period_end, datetime):
                period_end = datetime.combine(period_end, datetime.min.time())
            
            if period_end > now:
                days_remaining = (period_end - now).days
            else:
                # In grace period
                days_past = (now - period_end).days
                grace_period_remaining = max(0, 21 - days_past)
        
        # Generate message based on status
        messages = {
            "active": "Your subscription is active.",
            "trial": f"You have {days_remaining} days remaining in your trial.",
            "trial_expired": "Your trial has expired. Please subscribe to continue.",
            "trial_ended": "Your trial has ended. Please subscribe to continue.",
            "grace_period": f"Your payment is overdue. You have {grace_period_remaining} days to pay before service interruption.",
            "past_due": f"Your account is past due. Please pay immediately to avoid suspension. {grace_period_remaining} days remaining.",
            "suspended": "Your account has been suspended due to non-payment. Please contact billing.",
            "cancelled": "Your subscription has been cancelled.",
        }
        
        return {
            "has_access": has_access,
            "status": status,
            "tier": tenant_sku.tier.value if tenant_sku.tier else None,
            "message": messages.get(status, "Unknown subscription status"),
            "days_remaining": days_remaining,
            "grace_period_remaining": grace_period_remaining,
            "is_trial": tenant_sku.trial_ends_at is not None and tenant_sku.trial_ends_at > now,
        }
    
    async def cancel_subscription(
        self,
        organization_id: UUID,
        reason: Optional[str] = None,
        immediate: bool = False,
    ) -> Dict[str, Any]:
        """
        Cancel a subscription (downgrade to Core at end of period).
        
        The subscription remains active until the end of the current
        billing period, then downgrades to Core tier.
        
        Args:
            organization_id: Organization to cancel
            reason: Reason for cancellation
            immediate: If True, cancel immediately instead of at period end
            
        Returns:
            Dictionary with cancellation details
        """
        result = await self.db.execute(
            select(TenantSKU).where(
                and_(
                    TenantSKU.organization_id == organization_id,
                    TenantSKU.is_active == True,
                )
            )
        )
        tenant_sku = result.scalar_one_or_none()
        
        if not tenant_sku:
            return {"success": False, "message": "No active subscription found"}
        
        now = datetime.utcnow()
        previous_tier = tenant_sku.tier.value
        
        if immediate:
            # Immediately downgrade to Core
            tenant_sku.tier = SKUTier.CORE
            tenant_sku.intelligence_addon = None
            tenant_sku.cancel_at_period_end = False
            tenant_sku.cancellation_requested_at = now
            tenant_sku.cancellation_reason = reason or "User requested immediate cancellation"
            tenant_sku.scheduled_downgrade_tier = None
            tenant_sku.notes = f"Immediately cancelled on {now.strftime('%Y-%m-%d')}: {reason or 'User requested'}"
            
            await self.db.flush()
            
            # Send cancellation email
            await self._send_cancellation_email(organization_id, previous_tier, immediate=True)
            
            return {
                "success": True,
                "message": "Subscription has been cancelled and downgraded to Core",
                "previous_tier": previous_tier,
                "new_tier": SKUTier.CORE.value,
                "effective_immediately": True,
            }
        else:
            # Schedule cancellation at period end
            tenant_sku.cancel_at_period_end = True
            tenant_sku.cancellation_requested_at = now
            tenant_sku.cancellation_reason = reason or "User requested cancellation"
            tenant_sku.scheduled_downgrade_tier = SKUTier.CORE
            tenant_sku.notes = f"Scheduled for cancellation: {reason or 'User requested'}. Access until {tenant_sku.current_period_end.strftime('%Y-%m-%d') if tenant_sku.current_period_end else 'end of period'}."
            
            await self.db.flush()
            
            # Send scheduled cancellation email
            await self._send_cancellation_email(organization_id, previous_tier, immediate=False, period_end=tenant_sku.current_period_end)
            
            return {
                "success": True,
                "message": "Subscription will be cancelled at end of billing period",
                "previous_tier": previous_tier,
                "effective_date": tenant_sku.current_period_end.isoformat() if tenant_sku.current_period_end else None,
                "cancel_at_period_end": True,
            }
    
    async def _send_cancellation_email(
        self,
        organization_id: UUID,
        previous_tier: str,
        immediate: bool = False,
        period_end: Optional[datetime] = None,
    ) -> None:
        """Send cancellation confirmation email."""
        from app.services.billing_email_service import BillingEmailService
        from app.models.organization import Organization
        from app.models.user import User
        
        try:
            org_result = await self.db.execute(
                select(Organization).where(Organization.id == organization_id)
            )
            org = org_result.scalar_one_or_none()
            
            admin_result = await self.db.execute(
                select(User)
                .where(User.organization_id == organization_id)
                .where(User.is_active == True)
                .order_by(User.created_at)
                .limit(1)
            )
            admin_user = admin_result.scalar_one_or_none()
            
            if admin_user and admin_user.email and org:
                billing_email_service = BillingEmailService(self.db)
                
                if immediate:
                    # Use the trial_ended_downgrade template for immediate cancellation
                    await billing_email_service.send_trial_ended_downgrade(
                        email=admin_user.email,
                        organization_name=org.name,
                        previous_tier=previous_tier,
                    )
                else:
                    # Send scheduled cancellation notice
                    await billing_email_service.send_scheduled_cancellation(
                        email=admin_user.email,
                        organization_name=org.name,
                        tier=previous_tier,
                        effective_date=period_end,
                    )
        except Exception as e:
            logger.error(f"Failed to send cancellation email: {e}")
    
    async def reactivate_subscription(
        self,
        organization_id: UUID,
    ) -> Dict[str, Any]:
        """
        Reactivate a subscription that was scheduled for cancellation.
        
        This can only be done before the period end.
        """
        result = await self.db.execute(
            select(TenantSKU).where(
                and_(
                    TenantSKU.organization_id == organization_id,
                    TenantSKU.is_active == True,
                )
            )
        )
        tenant_sku = result.scalar_one_or_none()
        
        if not tenant_sku:
            return {"success": False, "message": "No active subscription found"}
        
        if not tenant_sku.cancel_at_period_end:
            return {"success": False, "message": "Subscription is not scheduled for cancellation"}
        
        # Clear cancellation flags
        tenant_sku.cancel_at_period_end = False
        tenant_sku.cancellation_requested_at = None
        tenant_sku.cancellation_reason = None
        tenant_sku.scheduled_downgrade_tier = None
        tenant_sku.notes = f"Cancellation reversed on {datetime.utcnow().strftime('%Y-%m-%d')}"
        
        await self.db.flush()
        
        return {
            "success": True,
            "message": "Subscription has been reactivated",
            "tier": tenant_sku.tier.value,
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def generate_payment_reference(
    organization_id: UUID,
    prefix: str = "TVP",
) -> str:
    """Generate a unique payment reference."""
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{organization_id.hex[:8]}-{timestamp}"


def format_price_naira(amount: int) -> str:
    """Format price in Naira."""
    return f"₦{amount:,}"


def calculate_annual_savings(
    tier: SKUTier,
) -> int:
    """Calculate savings from annual vs monthly billing."""
    pricing = TIER_PRICING.get(tier)
    if not pricing:
        return 0
    
    monthly_annual_cost = int(pricing.monthly_min) * 12
    actual_annual_cost = int(pricing.annual_min)
    
    return monthly_annual_cost - actual_annual_cost
