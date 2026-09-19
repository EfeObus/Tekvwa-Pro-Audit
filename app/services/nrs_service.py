"""
Tekvwa Pro Audit - NRS (FIRS) E-Invoicing Service

Integration with the Federal Inland Revenue Service (FIRS) e-invoicing system.

API Endpoints:
- Development/Sandbox: https://api-dev.i-fis.com
- Production: https://atrs-api.firs.gov.ng

Features:
- Invoice Reference Number (IRN) generation
- TIN validation
- QR code generation for invoices
- 72-hour buyer dispute window handling
"""

import uuid
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

import httpx
from pydantic import BaseModel, Field

from app.config import settings


class NRSEnvironment(str, Enum):
    """NRS API environment."""
    SANDBOX = "sandbox"
    PRODUCTION = "production"


class NRSErrorCode(str, Enum):
    """Common NRS error codes."""
    SUCCESS = "00"
    INVALID_TIN = "01"
    DUPLICATE_INVOICE = "02"
    INVALID_REQUEST = "03"
    AUTHENTICATION_FAILED = "04"
    RATE_LIMIT_EXCEEDED = "05"
    SERVER_ERROR = "99"


# ===========================================
# PYDANTIC MODELS FOR NRS API
# ===========================================

class NRSInvoiceLineItem(BaseModel):
    """Line item for NRS invoice submission."""
    item_description: str = Field(..., max_length=500)
    quantity: float
    unit_price: float
    vat_amount: float
    total_amount: float
    hsn_code: Optional[str] = None  # Harmonized System Code


class NRSInvoiceRequest(BaseModel):
    """Invoice submission request to NRS."""
    seller_tin: str
    seller_name: str
    seller_address: str
    buyer_tin: Optional[str] = None
    buyer_name: str
    buyer_address: Optional[str] = None
    invoice_number: str
    invoice_date: str  # YYYY-MM-DD
    invoice_type: str = "B2B"  # B2B or B2C
    currency: str = "NGN"
    subtotal: float
    vat_amount: float
    total_amount: float
    vat_rate: float = 7.5
    line_items: List[NRSInvoiceLineItem]


class NRSInvoiceResponse(BaseModel):
    """Response from NRS invoice submission."""
    success: bool
    response_code: str
    message: str
    irn: Optional[str] = None  # Invoice Reference Number
    qr_code_data: Optional[str] = None
    submission_timestamp: Optional[datetime] = None
    dispute_deadline: Optional[datetime] = None
    raw_response: Optional[Dict[str, Any]] = None


class NRSTINValidationRequest(BaseModel):
    """TIN validation request."""
    tin: str
    name: Optional[str] = None


class NRSTINValidationResponse(BaseModel):
    """TIN validation response."""
    is_valid: bool
    tin: str
    registered_name: Optional[str] = None
    business_type: Optional[str] = None
    registration_date: Optional[str] = None
    status: Optional[str] = None
    message: str
    raw_response: Optional[Dict[str, Any]] = None


class NRSDisputeRequest(BaseModel):
    """Buyer dispute request."""
    irn: str
    dispute_reason: str
    supporting_documents: Optional[List[str]] = None


class NRSDisputeResponse(BaseModel):
    """Dispute submission response."""
    success: bool
    message: str
    dispute_reference: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


# ===========================================
# NRS API CLIENT
# ===========================================

class NRSApiClient:
    """
    Client for interacting with the NRS (FIRS) e-invoicing API.
    
    Handles:
    - Invoice submission for IRN generation
    - TIN validation
    - QR code data generation
    - Dispute handling
    """
    
    # API Endpoints
    ENDPOINTS = {
        "invoice_submit": "/api/v1/invoice/submit",
        "invoice_status": "/api/v1/invoice/status",
        "tin_validate": "/api/v1/tin/validate",
        "tin_bulk_validate": "/api/v1/tin/bulk-validate",
        "dispute_submit": "/api/v1/dispute/submit",
        "dispute_status": "/api/v1/dispute/status",
    }
    
    # Timeout for API calls (seconds)
    REQUEST_TIMEOUT = 30
    
    def __init__(self, api_key: Optional[str] = None, sandbox_mode: Optional[bool] = None):
        """
        Initialize NRS API client.
        
        Args:
            api_key: API key for authentication. Defaults to settings.
            sandbox_mode: Whether to use sandbox. Defaults to settings.
        """
        self.api_key = api_key or settings.nrs_api_key
        self.sandbox_mode = sandbox_mode if sandbox_mode is not None else settings.nrs_sandbox_mode
        self.base_url = settings.nrs_api_url if self.sandbox_mode else settings.nrs_api_url_prod
    
    @property
    def environment(self) -> NRSEnvironment:
        """Get current environment."""
        return NRSEnvironment.SANDBOX if self.sandbox_mode else NRSEnvironment.PRODUCTION
    
    def _get_headers(self) -> Dict[str, str]:
        """Get API request headers."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "X-API-Version": "1.0",
            "X-Client-ID": "tekvwa-pro-audit",
        }
    
    def _generate_request_signature(self, payload: Dict[str, Any]) -> str:
        """
        Generate HMAC signature for request authentication.
        
        Some NRS implementations require request signing.
        """
        payload_str = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        signature = hmac.new(
            self.api_key.encode('utf-8'),
            payload_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Make HTTP request to NRS API.
        
        Returns:
            Tuple of (success, response_data)
        """
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()
        
        # Add request signature if payload exists
        if payload:
            headers["X-Request-Signature"] = self._generate_request_signature(payload)
        
        try:
            async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
                if method.upper() == "GET":
                    response = await client.get(url, headers=headers, params=payload)
                else:
                    response = await client.post(url, headers=headers, json=payload)
                
                response_data = response.json()
                
                # Check for successful response
                if response.status_code == 200:
                    return True, response_data
                else:
                    return False, {
                        "error": True,
                        "status_code": response.status_code,
                        "message": response_data.get("message", "Unknown error"),
                        "raw": response_data,
                    }
                    
        except httpx.TimeoutException:
            return False, {
                "error": True,
                "message": "Request timeout - NRS API did not respond in time",
            }
        except httpx.RequestError as e:
            return False, {
                "error": True,
                "message": f"Network error: {str(e)}",
            }
        except json.JSONDecodeError:
            return False, {
                "error": True,
                "message": "Invalid JSON response from NRS API",
            }
    
    # ===========================================
    # INVOICE OPERATIONS
    # ===========================================
    
    async def submit_invoice(
        self,
        seller_tin: str,
        seller_name: str,
        seller_address: str,
        buyer_name: str,
        invoice_number: str,
        invoice_date: str,
        subtotal: float,
        vat_amount: float,
        total_amount: float,
        line_items: List[Dict[str, Any]],
        buyer_tin: Optional[str] = None,
        buyer_address: Optional[str] = None,
        vat_rate: float = 7.5,
    ) -> NRSInvoiceResponse:
        """
        Submit invoice to NRS for IRN generation.
        
        B2B invoices require buyer TIN.
        B2C invoices don't require buyer TIN.
        
        Returns:
            NRSInvoiceResponse with IRN and QR code data if successful
        """
        # Determine invoice type
        invoice_type = "B2B" if buyer_tin else "B2C"
        
        # Prepare line items
        nrs_line_items = [
            {
                "item_description": item.get("description", ""),
                "quantity": item.get("quantity", 1),
                "unit_price": item.get("unit_price", 0),
                "vat_amount": item.get("vat_amount", 0),
                "total_amount": item.get("total", 0),
                "hsn_code": item.get("hsn_code"),
            }
            for item in line_items
        ]
        
        payload = {
            "seller_tin": seller_tin,
            "seller_name": seller_name,
            "seller_address": seller_address,
            "buyer_tin": buyer_tin,
            "buyer_name": buyer_name,
            "buyer_address": buyer_address,
            "invoice_number": invoice_number,
            "invoice_date": invoice_date,
            "invoice_type": invoice_type,
            "currency": "NGN",
            "subtotal": subtotal,
            "vat_amount": vat_amount,
            "total_amount": total_amount,
            "vat_rate": vat_rate,
            "line_items": nrs_line_items,
        }
        
        # In sandbox mode, simulate response
        if self.sandbox_mode and not self.api_key:
            return self._simulate_invoice_submission(invoice_number)
        
        success, response = await self._make_request(
            "POST",
            self.ENDPOINTS["invoice_submit"],
            payload,
        )
        
        if success:
            submission_time = datetime.utcnow()
            return NRSInvoiceResponse(
                success=True,
                response_code=response.get("response_code", NRSErrorCode.SUCCESS),
                message=response.get("message", "Invoice submitted successfully"),
                irn=response.get("irn"),
                qr_code_data=response.get("qr_code_data"),
                submission_timestamp=submission_time,
                dispute_deadline=submission_time + timedelta(hours=72),
                raw_response=response,
            )
        else:
            return NRSInvoiceResponse(
                success=False,
                response_code=response.get("response_code", NRSErrorCode.SERVER_ERROR),
                message=response.get("message", "Invoice submission failed"),
                raw_response=response,
            )
    
    def _simulate_invoice_submission(self, invoice_number: str) -> NRSInvoiceResponse:
        """
        Simulate invoice submission for sandbox/development.
        
        Generates realistic-looking IRN and QR code data.
        """
        # Generate simulated IRN
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        random_suffix = str(uuid.uuid4())[:8].upper()
        irn = f"NGN{timestamp}{random_suffix}"
        
        # Generate simulated QR code data
        qr_data = json.dumps({
            "irn": irn,
            "inv": invoice_number,
            "dt": datetime.utcnow().strftime("%Y-%m-%d"),
            "v": "1.0",
            "mode": "sandbox",
        })
        
        submission_time = datetime.utcnow()
        
        return NRSInvoiceResponse(
            success=True,
            response_code=NRSErrorCode.SUCCESS,
            message="Invoice submitted successfully (SANDBOX MODE)",
            irn=irn,
            qr_code_data=qr_data,
            submission_timestamp=submission_time,
            dispute_deadline=submission_time + timedelta(hours=72),
            raw_response={"sandbox": True, "simulated": True},
        )
    
    async def get_invoice_status(self, irn: str) -> Dict[str, Any]:
        """
        Get status of a submitted invoice by IRN.
        """
        if self.sandbox_mode and not self.api_key:
            return {
                "success": True,
                "irn": irn,
                "status": "ACCEPTED",
                "message": "Invoice status retrieved (SANDBOX MODE)",
            }
        
        success, response = await self._make_request(
            "GET",
            self.ENDPOINTS["invoice_status"],
            {"irn": irn},
        )
        
        return response
    
    # ===========================================
    # TIN VALIDATION
    # ===========================================
    
    async def validate_tin(
        self,
        tin: str,
        name: Optional[str] = None,
    ) -> NRSTINValidationResponse:
        """
        Validate a Tax Identification Number (TIN).
        
        Args:
            tin: The TIN to validate
            name: Optional business name to cross-verify
            
        Returns:
            NRSTINValidationResponse with validation result
        """
        # Basic TIN format validation (Nigerian TIN format)
        if not self._is_valid_tin_format(tin):
            return NRSTINValidationResponse(
                is_valid=False,
                tin=tin,
                message="Invalid TIN format. Nigerian TIN should be 10-14 digits.",
            )
        
        # In sandbox mode, simulate response
        if self.sandbox_mode and not self.api_key:
            return self._simulate_tin_validation(tin, name)
        
        payload = {
            "tin": tin,
            "name": name,
        }
        
        success, response = await self._make_request(
            "POST",
            self.ENDPOINTS["tin_validate"],
            payload,
        )
        
        if success:
            return NRSTINValidationResponse(
                is_valid=response.get("is_valid", False),
                tin=tin,
                registered_name=response.get("registered_name"),
                business_type=response.get("business_type"),
                registration_date=response.get("registration_date"),
                status=response.get("status"),
                message=response.get("message", "TIN validated"),
                raw_response=response,
            )
        else:
            return NRSTINValidationResponse(
                is_valid=False,
                tin=tin,
                message=response.get("message", "TIN validation failed"),
                raw_response=response,
            )
    
    def _is_valid_tin_format(self, tin: str) -> bool:
        """
        Check if TIN matches expected format.
        
        Nigerian TIN formats:
        - Personal: 10 digits
        - Corporate: 10-14 digits (with possible hyphens)
        """
        # Remove hyphens and spaces
        clean_tin = tin.replace("-", "").replace(" ", "")
        
        # Check if all digits
        if not clean_tin.isdigit():
            return False
        
        # Check length (10-14 digits)
        if len(clean_tin) < 10 or len(clean_tin) > 14:
            return False
        
        return True
    
    def _simulate_tin_validation(
        self,
        tin: str,
        name: Optional[str] = None,
    ) -> NRSTINValidationResponse:
        """
        Simulate TIN validation for sandbox/development.
        """
        # Simulate valid TIN for specific patterns
        clean_tin = tin.replace("-", "").replace(" ", "")
        
        # Simulate some TINs as valid, others as invalid
        is_valid = len(clean_tin) >= 10 and clean_tin[0] != "0"
        
        if is_valid:
            return NRSTINValidationResponse(
                is_valid=True,
                tin=tin,
                registered_name=name or f"Test Business {clean_tin[-4:]}",
                business_type="Corporate" if len(clean_tin) > 10 else "Individual",
                registration_date="2020-01-15",
                status="ACTIVE",
                message="TIN validated successfully (SANDBOX MODE)",
                raw_response={"sandbox": True, "simulated": True},
            )
        else:
            return NRSTINValidationResponse(
                is_valid=False,
                tin=tin,
                message="TIN not found in registry (SANDBOX MODE)",
                raw_response={"sandbox": True, "simulated": True},
            )
    
    async def bulk_validate_tins(
        self,
        tins: List[str],
    ) -> List[NRSTINValidationResponse]:
        """
        Validate multiple TINs in bulk.
        """
        results = []
        for tin in tins:
            result = await self.validate_tin(tin)
            results.append(result)
        return results
    
    # ===========================================
    # DISPUTE HANDLING
    # ===========================================
    
    async def submit_dispute(
        self,
        irn: str,
        dispute_reason: str,
        supporting_documents: Optional[List[str]] = None,
    ) -> NRSDisputeResponse:
        """
        Submit a buyer dispute for an invoice.
        
        Must be submitted within 72 hours of invoice acceptance.
        """
        if self.sandbox_mode and not self.api_key:
            return NRSDisputeResponse(
                success=True,
                message="Dispute submitted successfully (SANDBOX MODE)",
                dispute_reference=f"DISP-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                raw_response={"sandbox": True, "simulated": True},
            )
        
        payload = {
            "irn": irn,
            "dispute_reason": dispute_reason,
            "supporting_documents": supporting_documents or [],
        }
        
        success, response = await self._make_request(
            "POST",
            self.ENDPOINTS["dispute_submit"],
            payload,
        )
        
        if success:
            return NRSDisputeResponse(
                success=True,
                message=response.get("message", "Dispute submitted"),
                dispute_reference=response.get("dispute_reference"),
                raw_response=response,
            )
        else:
            return NRSDisputeResponse(
                success=False,
                message=response.get("message", "Dispute submission failed"),
                raw_response=response,
            )

    # ===========================================
    # B2C REAL-TIME REPORTING (2026 COMPLIANCE)
    # ===========================================
    
    async def submit_b2c_transaction_report(
        self,
        seller_tin: str,
        seller_name: str,
        transaction_date: str,
        transaction_reference: str,
        customer_name: str,
        transaction_amount: float,
        vat_amount: float,
        payment_method: str = "cash",
        customer_phone: Optional[str] = None,
        customer_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Submit B2C transaction for real-time reporting.
        
        2026 Compliance:
        - B2C transactions > ₦50,000 must be reported within 24 hours
        - Required for retail, hospitality, and consumer-facing businesses
        - Enables FIRS real-time monitoring of high-value B2C transactions
        
        Args:
            seller_tin: Seller's Tax Identification Number
            seller_name: Seller's registered name
            transaction_date: Date of transaction (YYYY-MM-DD)
            transaction_reference: Internal transaction reference
            customer_name: Customer name (can be "Walk-in Customer")
            transaction_amount: Total transaction amount
            vat_amount: VAT amount charged
            payment_method: Payment method (cash, card, transfer)
            customer_phone: Optional customer phone
            customer_email: Optional customer email
        
        Returns:
            Dict with submission result and B2C report reference
        """
        if self.sandbox_mode and not self.api_key:
            # Simulate B2C report submission
            report_ref = f"B2C-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:6].upper()}"
            return {
                "success": True,
                "message": "B2C transaction reported successfully (SANDBOX MODE)",
                "report_reference": report_ref,
                "reporting_deadline": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
                "amount_reported": transaction_amount,
                "sandbox": True,
            }
        
        payload = {
            "seller_tin": seller_tin,
            "seller_name": seller_name,
            "transaction_date": transaction_date,
            "transaction_reference": transaction_reference,
            "transaction_type": "B2C",
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "customer_email": customer_email,
            "transaction_amount": transaction_amount,
            "vat_amount": vat_amount,
            "payment_method": payment_method,
            "currency": "NGN",
            "reported_at": datetime.utcnow().isoformat(),
        }
        
        # B2C reporting endpoint (assuming NRS has this endpoint)
        b2c_endpoint = "/api/v1/b2c/report"
        
        success, response = await self._make_request(
            "POST",
            b2c_endpoint,
            payload,
        )
        
        if success:
            return {
                "success": True,
                "message": response.get("message", "B2C transaction reported"),
                "report_reference": response.get("report_reference"),
                "reported_at": datetime.utcnow().isoformat(),
            }
        else:
            return {
                "success": False,
                "message": response.get("message", "B2C reporting failed"),
                "error": response,
            }
    
    async def get_b2c_reporting_status(
        self,
        seller_tin: str,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """
        Get B2C reporting status for a date range.
        
        Shows:
        - Total transactions reported
        - Pending transactions (not yet reported)
        - Overdue transactions (past 24-hour deadline)
        """
        if self.sandbox_mode and not self.api_key:
            return {
                "success": True,
                "seller_tin": seller_tin,
                "period": {"start": start_date, "end": end_date},
                "summary": {
                    "total_transactions": 0,
                    "reported_on_time": 0,
                    "pending": 0,
                    "overdue": 0,
                    "total_amount_reported": 0,
                },
                "sandbox": True,
            }
        
        success, response = await self._make_request(
            "GET",
            "/api/v1/b2c/status",
            {
                "seller_tin": seller_tin,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        
        return response


# ===========================================
# SERVICE FACTORY
# ===========================================

def get_nrs_client(
    api_key: Optional[str] = None,
    sandbox_mode: Optional[bool] = None,
) -> NRSApiClient:
    """
    Factory function to get NRS API client.
    
    Uses settings by default, but allows overrides for testing.
    """
    return NRSApiClient(api_key=api_key, sandbox_mode=sandbox_mode)
