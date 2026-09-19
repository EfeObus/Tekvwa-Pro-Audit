"""
Comprehensive Error Handling Module for Tekvwa Pro Audit

This module provides robust, centralized error handling with:
- Custom exception hierarchy
- Standardized error responses
- Error logging and tracking
- Nigerian-specific validation errors
- Database and external service error handling
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Type, Union
from uuid import UUID
import traceback
import logging
import sys

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.exc import (
    SQLAlchemyError,
    IntegrityError,
    OperationalError,
    DataError,
    ProgrammingError,
    InterfaceError,
)
from starlette.exceptions import HTTPException as StarletteHTTPException

# Configure logging
logger = logging.getLogger("tekvwa.errors")


class ErrorCode(str, Enum):
    """Standardized error codes for the application"""
    
    # Validation Errors (4xx)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_FIELD = "MISSING_FIELD"
    INVALID_FORMAT = "INVALID_FORMAT"
    INVALID_TIN = "INVALID_TIN"
    INVALID_BVN = "INVALID_BVN"
    INVALID_ACCOUNT_NUMBER = "INVALID_ACCOUNT_NUMBER"
    INVALID_DATE_RANGE = "INVALID_DATE_RANGE"
    INVALID_AMOUNT = "INVALID_AMOUNT"
    INVALID_TAX_PERIOD = "INVALID_TAX_PERIOD"
    
    # Authentication/Authorization Errors (401/403)
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_INVALID = "TOKEN_INVALID"
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    ACCOUNT_DISABLED = "ACCOUNT_DISABLED"
    PASSWORD_RESET_REQUIRED = "PASSWORD_RESET_REQUIRED"
    MFA_REQUIRED = "MFA_REQUIRED"
    
    # Resource Errors (404/409)
    NOT_FOUND = "NOT_FOUND"
    ENTITY_NOT_FOUND = "ENTITY_NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    TRANSACTION_NOT_FOUND = "TRANSACTION_NOT_FOUND"
    INVOICE_NOT_FOUND = "INVOICE_NOT_FOUND"
    VENDOR_NOT_FOUND = "VENDOR_NOT_FOUND"
    CUSTOMER_NOT_FOUND = "CUSTOMER_NOT_FOUND"
    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"
    DUPLICATE_ENTRY = "DUPLICATE_ENTRY"
    DUPLICATE_TIN = "DUPLICATE_TIN"
    DUPLICATE_INVOICE = "DUPLICATE_INVOICE"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    
    # Business Logic Errors (422)
    BUSINESS_RULE_VIOLATION = "BUSINESS_RULE_VIOLATION"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    INSUFFICIENT_INVENTORY = "INSUFFICIENT_INVENTORY"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_DENIED = "APPROVAL_DENIED"
    ALREADY_PROCESSED = "ALREADY_PROCESSED"
    CANNOT_MODIFY = "CANNOT_MODIFY"
    CANNOT_DELETE = "CANNOT_DELETE"
    TAX_PERIOD_CLOSED = "TAX_PERIOD_CLOSED"
    WHT_CREDIT_EXPIRED = "WHT_CREDIT_EXPIRED"
    WHT_CREDIT_ALREADY_APPLIED = "WHT_CREDIT_ALREADY_APPLIED"
    MATCHING_DISCREPANCY = "MATCHING_DISCREPANCY"
    CHAIN_INTEGRITY_VIOLATED = "CHAIN_INTEGRITY_VIOLATED"
    
    # Rate Limiting (429)
    RATE_LIMITED = "RATE_LIMITED"
    TOO_MANY_REQUESTS = "TOO_MANY_REQUESTS"
    
    # External Service Errors (502/503)
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    FIRS_API_ERROR = "FIRS_API_ERROR"
    NIBSS_API_ERROR = "NIBSS_API_ERROR"
    BANK_API_ERROR = "BANK_API_ERROR"
    OPENAI_API_ERROR = "OPENAI_API_ERROR"
    EMAIL_SERVICE_ERROR = "EMAIL_SERVICE_ERROR"
    SMS_SERVICE_ERROR = "SMS_SERVICE_ERROR"
    
    # Database Errors (500)
    DATABASE_ERROR = "DATABASE_ERROR"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    TRANSACTION_ERROR = "TRANSACTION_ERROR"
    DATA_INTEGRITY_ERROR = "DATA_INTEGRITY_ERROR"
    
    # Internal Errors (500)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"


class AppException(Exception):
    """Base exception for all application exceptions"""
    
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
        field: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.field = field
        self.original_error = original_error
        self.timestamp = datetime.utcnow()
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for JSON response"""
        result = {
            "code": self.code.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat() + "Z",
        }
        if self.field:
            result["field"] = self.field
        if self.details:
            result["details"] = self.details
        return result


# ============================================================================
# Validation Exceptions
# ============================================================================

class ValidationException(AppException):
    """Base validation exception"""
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        code: ErrorCode = ErrorCode.VALIDATION_ERROR,
    ):
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
            field=field,
        )


class InvalidTINException(ValidationException):
    """Invalid Tax Identification Number"""
    
    def __init__(self, tin: str, message: Optional[str] = None):
        super().__init__(
            message=message or f"Invalid TIN format: {tin}. Expected 10 digits.",
            field="tin",
            code=ErrorCode.INVALID_TIN,
            details={"provided_tin": tin, "expected_format": "XXXXXXXXXX (10 digits)"},
        )


class InvalidBVNException(ValidationException):
    """Invalid Bank Verification Number"""
    
    def __init__(self, bvn: str, message: Optional[str] = None):
        super().__init__(
            message=message or f"Invalid BVN format: {bvn}. Expected 11 digits.",
            field="bvn",
            code=ErrorCode.INVALID_BVN,
            details={"provided_bvn": bvn, "expected_format": "XXXXXXXXXXX (11 digits)"},
        )


class InvalidAccountNumberException(ValidationException):
    """Invalid bank account number"""
    
    def __init__(self, account_number: str, message: Optional[str] = None):
        super().__init__(
            message=message or f"Invalid account number: {account_number}. Expected 10 digits (NUBAN).",
            field="account_number",
            code=ErrorCode.INVALID_ACCOUNT_NUMBER,
            details={"provided": account_number, "expected_format": "NUBAN (10 digits)"},
        )


class InvalidDateRangeException(ValidationException):
    """Invalid date range"""
    
    def __init__(self, start_date: str, end_date: str, message: Optional[str] = None):
        super().__init__(
            message=message or f"Invalid date range: {start_date} to {end_date}. Start date must be before end date.",
            code=ErrorCode.INVALID_DATE_RANGE,
            details={"start_date": start_date, "end_date": end_date},
        )


class InvalidAmountException(ValidationException):
    """Invalid monetary amount"""
    
    def __init__(self, amount: Any, field: str = "amount", message: Optional[str] = None):
        super().__init__(
            message=message or f"Invalid amount: {amount}. Amount must be a positive number.",
            field=field,
            code=ErrorCode.INVALID_AMOUNT,
            details={"provided_amount": str(amount)},
        )


# ============================================================================
# Authentication/Authorization Exceptions
# ============================================================================

class AuthenticationException(AppException):
    """Base authentication exception"""
    
    def __init__(
        self,
        message: str = "Authentication required",
        code: ErrorCode = ErrorCode.UNAUTHORIZED,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class TokenExpiredException(AuthenticationException):
    """Token has expired"""
    
    def __init__(self, message: str = "Access token has expired"):
        super().__init__(
            message=message,
            code=ErrorCode.TOKEN_EXPIRED,
            details={"action": "Please refresh your token or log in again"},
        )


class TokenInvalidException(AuthenticationException):
    """Token is invalid"""
    
    def __init__(self, message: str = "Invalid access token"):
        super().__init__(
            message=message,
            code=ErrorCode.TOKEN_INVALID,
        )


class AuthorizationException(AppException):
    """Authorization denied exception"""
    
    def __init__(
        self,
        message: str = "Permission denied",
        required_permission: Optional[str] = None,
        code: ErrorCode = ErrorCode.FORBIDDEN,
    ):
        details = {}
        if required_permission:
            details["required_permission"] = required_permission
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class InsufficientPermissionsException(AuthorizationException):
    """Insufficient permissions"""
    
    def __init__(self, required_permission: str, user_role: Optional[str] = None):
        details = {"required_permission": required_permission}
        if user_role:
            details["current_role"] = user_role
        super().__init__(
            message=f"Insufficient permissions. Required: {required_permission}",
            required_permission=required_permission,
            code=ErrorCode.INSUFFICIENT_PERMISSIONS,
        )


class AccountLockedException(AuthenticationException):
    """Account is locked"""
    
    def __init__(self, reason: str = "Too many failed login attempts"):
        super().__init__(
            message=f"Account is locked: {reason}",
            code=ErrorCode.ACCOUNT_LOCKED,
            details={"reason": reason, "action": "Contact administrator to unlock account"},
        )


# ============================================================================
# Resource Exceptions
# ============================================================================

class NotFoundException(AppException):
    """Resource not found exception"""
    
    def __init__(
        self,
        resource_type: str,
        resource_id: Optional[Union[str, UUID]] = None,
        message: Optional[str] = None,
        code: ErrorCode = ErrorCode.NOT_FOUND,
    ):
        if message is None:
            if resource_id:
                message = f"{resource_type} with ID '{resource_id}' not found"
            else:
                message = f"{resource_type} not found"
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            details={"resource_type": resource_type, "resource_id": str(resource_id) if resource_id else None},
        )


class EntityNotFoundException(NotFoundException):
    """Entity not found"""
    
    def __init__(self, entity_id: Union[str, UUID]):
        super().__init__(
            resource_type="Entity",
            resource_id=entity_id,
            code=ErrorCode.ENTITY_NOT_FOUND,
        )


class TransactionNotFoundException(NotFoundException):
    """Transaction not found"""
    
    def __init__(self, transaction_id: Union[str, UUID]):
        super().__init__(
            resource_type="Transaction",
            resource_id=transaction_id,
            code=ErrorCode.TRANSACTION_NOT_FOUND,
        )


class UserNotFoundException(NotFoundException):
    """User not found"""
    
    def __init__(self, user_id: Optional[Union[str, UUID]] = None, email: Optional[str] = None):
        if email:
            super().__init__(
                resource_type="User",
                message=f"User with email '{email}' not found",
                code=ErrorCode.USER_NOT_FOUND,
            )
        else:
            super().__init__(
                resource_type="User",
                resource_id=user_id,
                code=ErrorCode.USER_NOT_FOUND,
            )


class ConflictException(AppException):
    """Resource conflict exception"""
    
    def __init__(
        self,
        message: str,
        resource_type: Optional[str] = None,
        code: ErrorCode = ErrorCode.RESOURCE_CONFLICT,
        details: Optional[Dict[str, Any]] = None,
    ):
        _details = details or {}
        if resource_type:
            _details["resource_type"] = resource_type
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=_details,
        )


class DuplicateEntryException(ConflictException):
    """Duplicate entry exception"""
    
    def __init__(
        self,
        resource_type: str,
        field: str,
        value: str,
    ):
        super().__init__(
            message=f"{resource_type} with {field} '{value}' already exists",
            resource_type=resource_type,
            code=ErrorCode.DUPLICATE_ENTRY,
            details={"field": field, "value": value},
        )


# ============================================================================
# Business Logic Exceptions
# ============================================================================

class BusinessRuleException(AppException):
    """Business rule violation exception"""
    
    def __init__(
        self,
        message: str,
        rule: Optional[str] = None,
        code: ErrorCode = ErrorCode.BUSINESS_RULE_VIOLATION,
        details: Optional[Dict[str, Any]] = None,
    ):
        _details = details or {}
        if rule:
            _details["violated_rule"] = rule
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=_details,
        )


class InsufficientFundsException(BusinessRuleException):
    """Insufficient funds exception"""
    
    def __init__(self, required: float, available: float, currency: str = "NGN"):
        super().__init__(
            message=f"Insufficient funds. Required: {currency} {required:,.2f}, Available: {currency} {available:,.2f}",
            rule="SUFFICIENT_FUNDS_REQUIRED",
            code=ErrorCode.INSUFFICIENT_FUNDS,
            details={
                "required_amount": required,
                "available_amount": available,
                "currency": currency,
                "shortfall": required - available,
            },
        )


class InsufficientInventoryException(BusinessRuleException):
    """Insufficient inventory exception"""
    
    def __init__(self, item_name: str, required: float, available: float, unit: str = "units"):
        super().__init__(
            message=f"Insufficient inventory for '{item_name}'. Required: {required} {unit}, Available: {available} {unit}",
            rule="SUFFICIENT_INVENTORY_REQUIRED",
            code=ErrorCode.INSUFFICIENT_INVENTORY,
            details={
                "item": item_name,
                "required_quantity": required,
                "available_quantity": available,
                "unit": unit,
                "shortfall": required - available,
            },
        )


class BudgetExceededException(BusinessRuleException):
    """Budget exceeded exception"""
    
    def __init__(self, budget_name: str, budget_amount: float, requested_amount: float, currency: str = "NGN"):
        super().__init__(
            message=f"Budget '{budget_name}' would be exceeded. Budget: {currency} {budget_amount:,.2f}, Requested: {currency} {requested_amount:,.2f}",
            rule="BUDGET_LIMIT",
            code=ErrorCode.BUDGET_EXCEEDED,
            details={
                "budget_name": budget_name,
                "budget_amount": budget_amount,
                "requested_amount": requested_amount,
                "currency": currency,
                "overage": requested_amount - budget_amount,
            },
        )


class ApprovalRequiredException(BusinessRuleException):
    """Approval required exception"""
    
    def __init__(self, operation: str, approval_type: str):
        super().__init__(
            message=f"Approval required for {operation}. Please submit for {approval_type} approval.",
            rule="APPROVAL_REQUIRED",
            code=ErrorCode.APPROVAL_REQUIRED,
            details={"operation": operation, "approval_type": approval_type},
        )


class TaxPeriodClosedException(BusinessRuleException):
    """Tax period closed exception"""
    
    def __init__(self, period: str, operation: str = "modification"):
        super().__init__(
            message=f"Cannot perform {operation} on closed tax period: {period}",
            rule="TAX_PERIOD_OPEN",
            code=ErrorCode.TAX_PERIOD_CLOSED,
            details={"tax_period": period, "operation": operation},
        )


class WHTCreditExpiredException(BusinessRuleException):
    """WHT credit expired exception"""
    
    def __init__(self, certificate_number: str, expiry_date: str):
        super().__init__(
            message=f"WHT credit note '{certificate_number}' expired on {expiry_date}",
            rule="WHT_CREDIT_VALID",
            code=ErrorCode.WHT_CREDIT_EXPIRED,
            details={"certificate_number": certificate_number, "expiry_date": expiry_date},
        )


class MatchingDiscrepancyException(BusinessRuleException):
    """Matching discrepancy exception"""
    
    def __init__(self, discrepancies: list, match_type: str = "three-way"):
        super().__init__(
            message=f"{match_type.title()} matching failed due to discrepancies",
            rule="MATCHING_TOLERANCE",
            code=ErrorCode.MATCHING_DISCREPANCY,
            details={"match_type": match_type, "discrepancies": discrepancies},
        )


class ChainIntegrityException(BusinessRuleException):
    """Ledger chain integrity violation"""
    
    def __init__(self, entry_id: str, expected_hash: str, actual_hash: str):
        super().__init__(
            message="Immutable ledger chain integrity violated",
            rule="CHAIN_INTEGRITY",
            code=ErrorCode.CHAIN_INTEGRITY_VIOLATED,
            details={
                "entry_id": entry_id,
                "expected_hash": expected_hash[:16] + "...",
                "actual_hash": actual_hash[:16] + "...",
            },
        )


# ============================================================================
# External Service Exceptions
# ============================================================================

class ExternalServiceException(AppException):
    """External service error exception"""
    
    def __init__(
        self,
        service_name: str,
        message: str,
        code: ErrorCode = ErrorCode.EXTERNAL_SERVICE_ERROR,
        original_error: Optional[Exception] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        _details = details or {}
        _details["service"] = service_name
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
            details=_details,
            original_error=original_error,
        )


class FIRSAPIException(ExternalServiceException):
    """FIRS API error"""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(
            service_name="FIRS API",
            message=f"FIRS API error: {message}",
            code=ErrorCode.FIRS_API_ERROR,
            original_error=original_error,
        )


class NIBSSAPIException(ExternalServiceException):
    """NIBSS API error"""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(
            service_name="NIBSS API",
            message=f"NIBSS API error: {message}",
            code=ErrorCode.NIBSS_API_ERROR,
            original_error=original_error,
        )


class OpenAIAPIException(ExternalServiceException):
    """OpenAI API error"""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(
            service_name="OpenAI API",
            message=f"AI service error: {message}",
            code=ErrorCode.OPENAI_API_ERROR,
            original_error=original_error,
        )


# ============================================================================
# Database Exceptions
# ============================================================================

class DatabaseException(AppException):
    """Database error exception"""
    
    def __init__(
        self,
        message: str = "A database error occurred",
        code: ErrorCode = ErrorCode.DATABASE_ERROR,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            original_error=original_error,
        )


class ConnectionException(DatabaseException):
    """Database connection error"""
    
    def __init__(self, message: str = "Unable to connect to database", original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            code=ErrorCode.CONNECTION_ERROR,
            original_error=original_error,
        )


class DataIntegrityException(DatabaseException):
    """Data integrity error"""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            code=ErrorCode.DATA_INTEGRITY_ERROR,
            original_error=original_error,
        )


# ============================================================================
# Rate Limiting Exception
# ============================================================================

class RateLimitException(AppException):
    """Rate limit exceeded"""
    
    def __init__(self, retry_after: int = 60):
        super().__init__(
            code=ErrorCode.RATE_LIMITED,
            message=f"Rate limit exceeded. Please try again in {retry_after} seconds.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"retry_after_seconds": retry_after},
        )


# ============================================================================
# Exception Handlers
# ============================================================================

def create_error_response(
    code: ErrorCode,
    message: str,
    status_code: int,
    details: Optional[Dict[str, Any]] = None,
    field: Optional[str] = None,
) -> JSONResponse:
    """Create a standardized error response"""
    content = {
        "detail": {
            "code": code.value,
            "message": message,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    }
    if field:
        content["detail"]["field"] = field
    if details:
        content["detail"]["details"] = details
    
    return JSONResponse(status_code=status_code, content=content)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle AppException"""
    # Log the error
    logger.error(
        f"AppException: {exc.code.value} - {exc.message}",
        extra={
            "code": exc.code.value,
            "path": request.url.path,
            "method": request.method,
            "details": exc.details,
        },
        exc_info=exc.original_error,
    )
    
    return create_error_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
        field=exc.field,
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTPException"""
    # Map status codes to error codes
    code_map = {
        400: ErrorCode.INVALID_INPUT,
        401: ErrorCode.UNAUTHORIZED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        409: ErrorCode.RESOURCE_CONFLICT,
        422: ErrorCode.VALIDATION_ERROR,
        429: ErrorCode.RATE_LIMITED,
        500: ErrorCode.INTERNAL_ERROR,
        502: ErrorCode.EXTERNAL_SERVICE_ERROR,
        503: ErrorCode.EXTERNAL_SERVICE_ERROR,
    }
    
    error_code = code_map.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    
    logger.warning(
        f"HTTPException: {exc.status_code} - {message}",
        extra={"path": request.url.path, "method": request.method},
    )
    
    return create_error_response(
        code=error_code,
        message=message,
        status_code=exc.status_code,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle Pydantic validation errors"""
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"],
        })
    
    logger.warning(
        f"ValidationError: {len(errors)} validation errors",
        extra={"path": request.url.path, "method": request.method, "errors": errors},
    )
    
    return create_error_response(
        code=ErrorCode.VALIDATION_ERROR,
        message="Request validation failed",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details={"errors": errors},
    )


async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Handle SQLAlchemy errors"""
    error_message = "A database error occurred"
    error_code = ErrorCode.DATABASE_ERROR
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    
    if isinstance(exc, IntegrityError):
        error_message = "Data integrity constraint violated"
        error_code = ErrorCode.DATA_INTEGRITY_ERROR
        # Check for specific constraints
        error_str = str(exc.orig).lower() if exc.orig else ""
        if "unique" in error_str or "duplicate" in error_str:
            error_message = "A record with this value already exists"
            error_code = ErrorCode.DUPLICATE_ENTRY
            status_code = status.HTTP_409_CONFLICT
        elif "foreign key" in error_str:
            error_message = "Referenced record does not exist"
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    elif isinstance(exc, OperationalError):
        error_message = "Database operation failed"
        error_code = ErrorCode.CONNECTION_ERROR
    elif isinstance(exc, DataError):
        error_message = "Invalid data format for database"
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    
    logger.error(
        f"SQLAlchemyError: {type(exc).__name__} - {str(exc)}",
        extra={"path": request.url.path, "method": request.method},
        exc_info=True,
    )
    
    return create_error_response(
        code=error_code,
        message=error_message,
        status_code=status_code,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unhandled exceptions"""
    logger.critical(
        f"UnhandledException: {type(exc).__name__} - {str(exc)}",
        extra={"path": request.url.path, "method": request.method},
        exc_info=True,
    )
    
    # In production, don't expose internal error details
    return create_error_response(
        code=ErrorCode.INTERNAL_ERROR,
        message="An unexpected error occurred. Please try again later.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers with the FastAPI application"""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


# ============================================================================
# Error Tracking Middleware
# ============================================================================

class ErrorTrackingMiddleware:
    """Middleware for tracking and logging all errors"""
    
    def __init__(self, app: FastAPI):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        try:
            await self.app(scope, receive, send)
        except Exception as exc:
            # Log error with request context
            logger.error(
                f"Request failed: {scope.get('path', 'unknown')}",
                extra={
                    "path": scope.get("path"),
                    "method": scope.get("method"),
                    "exception_type": type(exc).__name__,
                },
                exc_info=True,
            )
            raise


# ============================================================================
# Utility Functions
# ============================================================================

def validate_tin(tin: str) -> str:
    """Validate and clean Nigerian TIN"""
    cleaned = tin.replace("-", "").replace(" ", "")
    if len(cleaned) != 10 or not cleaned.isdigit():
        raise InvalidTINException(tin)
    return cleaned


def validate_bvn(bvn: str) -> str:
    """Validate and clean Nigerian BVN"""
    cleaned = bvn.replace("-", "").replace(" ", "")
    if len(cleaned) != 11 or not cleaned.isdigit():
        raise InvalidBVNException(bvn)
    return cleaned


def validate_account_number(account_number: str) -> str:
    """Validate Nigerian NUBAN account number"""
    cleaned = account_number.replace("-", "").replace(" ", "")
    if len(cleaned) != 10 or not cleaned.isdigit():
        raise InvalidAccountNumberException(account_number)
    return cleaned


def validate_amount(amount: Any, field: str = "amount", allow_zero: bool = False) -> float:
    """Validate monetary amount"""
    try:
        value = float(amount)
        if value < 0 or (not allow_zero and value == 0):
            raise InvalidAmountException(amount, field)
        return value
    except (TypeError, ValueError):
        raise InvalidAmountException(amount, field)


# Export all exceptions for easy importing
__all__ = [
    # Base
    "AppException",
    "ErrorCode",
    
    # Validation
    "ValidationException",
    "InvalidTINException",
    "InvalidBVNException",
    "InvalidAccountNumberException",
    "InvalidDateRangeException",
    "InvalidAmountException",
    
    # Auth
    "AuthenticationException",
    "TokenExpiredException",
    "TokenInvalidException",
    "AuthorizationException",
    "InsufficientPermissionsException",
    "AccountLockedException",
    
    # Resource
    "NotFoundException",
    "EntityNotFoundException",
    "TransactionNotFoundException",
    "UserNotFoundException",
    "ConflictException",
    "DuplicateEntryException",
    
    # Business Logic
    "BusinessRuleException",
    "InsufficientFundsException",
    "InsufficientInventoryException",
    "BudgetExceededException",
    "ApprovalRequiredException",
    "TaxPeriodClosedException",
    "WHTCreditExpiredException",
    "MatchingDiscrepancyException",
    "ChainIntegrityException",
    
    # External Services
    "ExternalServiceException",
    "FIRSAPIException",
    "NIBSSAPIException",
    "OpenAIAPIException",
    
    # Database
    "DatabaseException",
    "ConnectionException",
    "DataIntegrityException",
    
    # Rate Limiting
    "RateLimitException",
    
    # Handlers
    "setup_exception_handlers",
    "create_error_response",
    "ErrorTrackingMiddleware",
    
    # Utilities
    "validate_tin",
    "validate_bvn",
    "validate_account_number",
    "validate_amount",
]
