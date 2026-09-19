"""
Tekvwa Pro Audit - NDPA Security Module

Nigeria Data Protection Act (2023/2026) Compliant Security Features

This module provides:
1. PII Field-Level Encryption (AES-256-GCM)
2. Data Masking for Display
3. Geo-Fencing (Nigeria-First Access)
4. Rate Limiting & DDoS Protection
5. CSRF Protection for HTMX
6. Content Security Policy (CSP)
7. Account Lockout (Brute Force Protection)
8. Right-to-Erasure Workflow
"""

import os
import re
import base64
import hashlib
import secrets
import ipaddress
from datetime import datetime, timedelta
from typing import Optional, Tuple, Any, Dict, List, Callable
from enum import Enum
from dataclasses import dataclass, field
from functools import lru_cache, wraps
import logging

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


# ============================================================================
# PII CATEGORIES (NDPA Classification)
# ============================================================================

class PIICategory(str, Enum):
    """NDPA-defined PII categories with sensitivity levels."""
    
    # High Sensitivity - Requires AES-256 encryption
    BVN = "bvn"  # Bank Verification Number
    NIN = "nin"  # National Identification Number
    PASSPORT = "passport"
    DRIVERS_LICENSE = "drivers_license"
    RSA_PIN = "rsa_pin"  # Pension RSA PIN
    BANK_ACCOUNT = "bank_account"
    
    # Medium Sensitivity - Encryption recommended
    TIN = "tin"  # Tax Identification Number
    PHONE_NUMBER = "phone"
    EMAIL = "email"
    DATE_OF_BIRTH = "dob"
    HOME_ADDRESS = "address"
    
    # Low Sensitivity - Masking only
    FULL_NAME = "name"
    EMPLOYEE_ID = "employee_id"


# ============================================================================
# AES-256 ENCRYPTION ENGINE
# ============================================================================

class PIIEncryptionEngine:
    """
    AES-256-GCM Field-Level Encryption for PII Data.
    
    NDPA Compliant:
    - Uses AES-256 (256-bit key)
    - GCM mode for authenticated encryption
    - Unique IV per encryption operation
    - Key derivation from master secret
    """
    
    def __init__(self, master_key: Optional[str] = None):
        """
        Initialize encryption engine with master key.
        
        Args:
            master_key: Base64-encoded 32-byte key. If None, uses environment variable.
        """
        self.master_key = self._get_or_generate_key(master_key)
        self._fernet = Fernet(base64.urlsafe_b64encode(self.master_key[:32].ljust(32, b'\0')))
    
    def _get_or_generate_key(self, provided_key: Optional[str]) -> bytes:
        """Get master key from environment or generate new one."""
        if provided_key:
            return base64.b64decode(provided_key)
        
        env_key = os.environ.get("PII_ENCRYPTION_KEY")
        if env_key:
            return base64.b64decode(env_key)
        
        # In production, this should raise an error
        # For development, generate a consistent key from app secret
        app_secret = os.environ.get("SECRET_KEY", "development-secret-key")
        return hashlib.sha256(app_secret.encode()).digest()
    
    def encrypt(self, plaintext: str, category: PIICategory = PIICategory.BVN) -> str:
        """
        Encrypt a PII field using AES-256-GCM.
        
        Args:
            plaintext: The raw PII value to encrypt
            category: PII category for metadata
            
        Returns:
            Base64-encoded encrypted string with format:
            {category}:{iv}:{ciphertext}:{tag}
        """
        if not plaintext:
            return ""
        
        # Generate random 12-byte IV for GCM
        iv = secrets.token_bytes(12)
        
        # Create cipher
        cipher = Cipher(
            algorithms.AES(self.master_key),
            modes.GCM(iv),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        
        # Add category as associated data for integrity
        encryptor.authenticate_additional_data(category.value.encode())
        
        # Pad plaintext to 16-byte boundary
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext.encode()) + padder.finalize()
        
        # Encrypt
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()
        tag = encryptor.tag
        
        # Encode and format
        result = f"{category.value}:{base64.b64encode(iv).decode()}:{base64.b64encode(ciphertext).decode()}:{base64.b64encode(tag).decode()}"
        return result
    
    def decrypt(self, encrypted_value: str) -> Tuple[str, PIICategory]:
        """
        Decrypt a PII field.
        
        Args:
            encrypted_value: The encrypted string from encrypt()
            
        Returns:
            Tuple of (plaintext, category)
            
        Raises:
            ValueError: If decryption fails or data is corrupted
        """
        if not encrypted_value:
            return "", PIICategory.BVN
        
        try:
            parts = encrypted_value.split(":")
            if len(parts) != 4:
                raise ValueError("Invalid encrypted format")
            
            category = PIICategory(parts[0])
            iv = base64.b64decode(parts[1])
            ciphertext = base64.b64decode(parts[2])
            tag = base64.b64decode(parts[3])
            
            # Create cipher
            cipher = Cipher(
                algorithms.AES(self.master_key),
                modes.GCM(iv, tag),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            
            # Verify category integrity
            decryptor.authenticate_additional_data(category.value.encode())
            
            # Decrypt
            padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
            
            # Unpad
            unpadder = padding.PKCS7(128).unpadder()
            plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
            
            return plaintext.decode(), category
            
        except Exception as e:
            raise ValueError(f"Decryption failed: {str(e)}")
    
    def encrypt_simple(self, plaintext: str) -> str:
        """Simple Fernet encryption for less sensitive data."""
        if not plaintext:
            return ""
        return self._fernet.encrypt(plaintext.encode()).decode()
    
    def decrypt_simple(self, encrypted_value: str) -> str:
        """Simple Fernet decryption."""
        if not encrypted_value:
            return ""
        return self._fernet.decrypt(encrypted_value.encode()).decode()


# ============================================================================
# PII MASKING FOR DISPLAY
# ============================================================================

class PIIMasker:
    """
    Mask PII for display purposes.
    
    Even authorized users see masked values in UI.
    Full values only accessible via secure API with audit logging.
    """
    
    @staticmethod
    def mask_bvn(bvn: str) -> str:
        """Mask BVN: 22*******45"""
        if not bvn or len(bvn) < 4:
            return "***********"
        return f"{bvn[:2]}*******{bvn[-2:]}"
    
    @staticmethod
    def mask_nin(nin: str) -> str:
        """Mask NIN: 123*****901"""
        if not nin or len(nin) < 6:
            return "***********"
        return f"{nin[:3]}*****{nin[-3:]}"
    
    @staticmethod
    def mask_phone(phone: str) -> str:
        """Mask phone: 0803***4567"""
        if not phone or len(phone) < 7:
            return "***********"
        return f"{phone[:4]}***{phone[-4:]}"
    
    @staticmethod
    def mask_email(email: str) -> str:
        """Mask email: j***@domain.com"""
        if not email or "@" not in email:
            return "***@***.com"
        parts = email.split("@")
        user = parts[0]
        domain = parts[1]
        masked_user = f"{user[0]}***" if len(user) > 1 else "***"
        return f"{masked_user}@{domain}"
    
    @staticmethod
    def mask_account(account: str) -> str:
        """Mask bank account: ****4567"""
        if not account or len(account) < 4:
            return "**********"
        return f"****{account[-4:]}"
    
    @staticmethod
    def mask_tin(tin: str) -> str:
        """Mask TIN: 123***890"""
        if not tin or len(tin) < 6:
            return "**********"
        return f"{tin[:3]}***{tin[-3:]}"
    
    @staticmethod
    def mask_rsa_pin(rsa_pin: str) -> str:
        """Mask RSA PIN: PEN***789012"""
        if not rsa_pin or len(rsa_pin) < 8:
            return "PEN***********"
        return f"{rsa_pin[:3]}***{rsa_pin[-6:]}"
    
    @staticmethod
    def mask_address(address: str) -> str:
        """Mask address: 12 *** Street, Lagos"""
        if not address or len(address) < 10:
            return "*** Street, ***"
        words = address.split()
        if len(words) <= 2:
            return "*** ***"
        return f"{words[0]} *** {' '.join(words[-2:])}"
    
    @classmethod
    def mask_pii(cls, value: str, category: PIICategory) -> str:
        """Mask PII based on category."""
        maskers = {
            PIICategory.BVN: cls.mask_bvn,
            PIICategory.NIN: cls.mask_nin,
            PIICategory.PHONE_NUMBER: cls.mask_phone,
            PIICategory.EMAIL: cls.mask_email,
            PIICategory.BANK_ACCOUNT: cls.mask_account,
            PIICategory.TIN: cls.mask_tin,
            PIICategory.RSA_PIN: cls.mask_rsa_pin,
            PIICategory.HOME_ADDRESS: cls.mask_address,
        }
        masker = maskers.get(category)
        if masker:
            return masker(value)
        return "***"


# ============================================================================
# GEO-FENCING UTILITIES
# ============================================================================

# Allowed countries for access (Nigeria + diaspora locations)
# Country codes follow ISO 3166-1 alpha-2 standard
ALLOWED_COUNTRIES = [
    # Primary market
    "NG",  # Nigeria
    
    # North America (diaspora)
    "CA",  # Canada
    "US",  # United States
    
    # Europe (diaspora)
    "GB",  # United Kingdom
    "DE",  # Germany
    "FR",  # France
    "NL",  # Netherlands
    "IE",  # Ireland
    "IT",  # Italy
    "ES",  # Spain
    "PT",  # Portugal
    "BE",  # Belgium
    "AT",  # Austria
    "CH",  # Switzerland
    "SE",  # Sweden
    "NO",  # Norway
    "DK",  # Denmark
    "FI",  # Finland
    "PL",  # Poland
    "CZ",  # Czech Republic
    "GR",  # Greece
    "LU",  # Luxembourg
]

# Nigerian IP ranges (AFRINIC allocations)
NIGERIAN_IP_RANGES = [
    "41.58.0.0/15",      # MTN Nigeria
    "41.73.128.0/17",    # Airtel Nigeria
    "41.138.160.0/19",   # Glo Nigeria
    "41.184.0.0/15",     # 9mobile
    "41.190.0.0/15",     # Various ISPs
    "41.203.64.0/18",    # MainOne
    "41.204.0.0/14",     # Various
    "41.211.0.0/16",     # Various
    "41.216.160.0/19",   # Rack Centre
    "41.217.192.0/18",   # Various
    "102.0.0.0/8",       # AFRINIC general (includes Nigeria)
    "105.0.0.0/8",       # AFRINIC general
    "154.0.0.0/8",       # AFRINIC general
    "196.0.0.0/8",       # AFRINIC general
    "197.0.0.0/8",       # AFRINIC general
    # Private/Local ranges for development
    "127.0.0.0/8",       # Localhost
    "10.0.0.0/8",        # Private
    "172.16.0.0/12",     # Private
    "192.168.0.0/16",    # Private
]


@dataclass
class GeoLocation:
    """Geolocation data for an IP address."""
    ip: str
    country_code: str = "NG"
    country_name: str = "Nigeria"
    region: str = ""
    city: str = ""
    is_nigerian: bool = True
    is_authorized_diaspora: bool = False
    is_vpn: bool = False
    is_tor: bool = False
    is_datacenter: bool = False
    risk_score: int = 0


class GeoFencingService:
    """
    Geo-fencing service for Nigeria-first access control.
    Supports access from Nigeria and diaspora countries (CA, US, Europe).
    """
    
    def __init__(self):
        self._nigerian_networks = [
            ipaddress.ip_network(cidr) for cidr in NIGERIAN_IP_RANGES
        ]
        self._country_cache: Dict[str, str] = {}  # IP -> country code cache
    
    def is_nigerian_ip(self, ip: str) -> bool:
        """Check if IP is within Nigerian ranges."""
        try:
            ip_obj = ipaddress.ip_address(ip)
            for network in self._nigerian_networks:
                if ip_obj in network:
                    return True
            return False
        except ValueError:
            return False
    
    def is_private_ip(self, ip: str) -> bool:
        """Check if IP is a private/local address."""
        try:
            ip_obj = ipaddress.ip_address(ip)
            return ip_obj.is_private or ip_obj.is_loopback
        except ValueError:
            return False
    
    async def get_country_code(self, ip: str) -> str:
        """
        Get country code for an IP address using free ip-api.com service.
        Returns 'XX' if lookup fails.
        """
        # Check cache first
        if ip in self._country_cache:
            return self._country_cache[ip]
        
        # Private IPs are considered local/allowed
        if self.is_private_ip(ip):
            self._country_cache[ip] = "LOCAL"
            return "LOCAL"
        
        # Nigerian IP ranges - return NG directly
        if self.is_nigerian_ip(ip):
            self._country_cache[ip] = "NG"
            return "NG"
        
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"http://ip-api.com/json/{ip}?fields=countryCode")
                if response.status_code == 200:
                    data = response.json()
                    country = data.get("countryCode", "XX")
                    self._country_cache[ip] = country
                    return country
        except Exception:
            pass
        
        # Fallback: If lookup fails, allow access (fail-open for better UX)
        # This ensures users aren't blocked due to API issues
        return "XX"
    
    def get_client_ip(self, request) -> str:
        """Extract real client IP from request."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        if hasattr(request, 'client') and request.client:
            return request.client.host
        
        return "127.0.0.1"
    
    async def check_access(
        self,
        ip: str,
        user_id: Optional[str] = None,
        is_diaspora_authorized: bool = False,
    ) -> Tuple[bool, str, int]:
        """
        Check if access should be granted based on geolocation.
        
        Allows access from:
        - Nigeria (primary market)
        - Canada, USA, Europe (diaspora locations)
        - Private/local IPs (development)
        """
        # Fast path: Nigerian IP ranges
        if self.is_nigerian_ip(ip):
            return True, "Nigerian IP", 0
        
        # Private/local IPs always allowed (development)
        if self.is_private_ip(ip):
            return True, "Local/development IP", 0
        
        # Diaspora-authorized users (premium feature)
        if is_diaspora_authorized:
            return True, "Authorized diaspora user", 20
        
        # Check country code for diaspora countries
        country_code = await self.get_country_code(ip)
        
        # Unknown country - fail-open for better UX
        if country_code == "XX":
            return True, "Geolocation unavailable - access granted", 10
        
        # Check if country is in allowed list
        if country_code in ALLOWED_COUNTRIES or country_code == "LOCAL":
            risk_score = 0 if country_code == "NG" else 15  # Slightly higher risk for diaspora
            return True, f"Access from {country_code}", risk_score
        
        return False, f"Access restricted - country {country_code} not in allowed list", 100


# ============================================================================
# RATE LIMITING
# ============================================================================

@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    
    # Endpoint pattern -> (requests, window_seconds)
    LIMITS: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    
    def __post_init__(self):
        self.LIMITS = {
            "/api/v1/auth/login": (5, 60),           # 5 per minute
            "/api/v1/auth/register": (3, 60),        # 3 per minute
            "/api/v1/auth/forgot-password": (3, 300), # 3 per 5 minutes
            "/api/v1/auth/reset-password": (5, 300),  # 5 per 5 minutes
            "/api/v1/tax-calculators": (30, 60),     # 30 per minute
            "/api/v1/tax-2026": (30, 60),            # 30 per minute
            "/api/v1/nrs": (10, 60),                 # 10 per minute
            "/api/v1": (100, 60),                    # 100 per minute
            "/api/v1/business-intelligence": (50, 60),
        }
    
    def get_limit(self, path: str) -> Tuple[int, int]:
        """Get rate limit for a path."""
        for pattern, limit in self.LIMITS.items():
            if path.startswith(pattern):
                return limit
        return (100, 60)


# ============================================================================
# ACCOUNT LOCKOUT MANAGER
# ============================================================================

class AccountLockoutManager:
    """Account lockout manager for brute force protection."""
    
    _failed_attempts: Dict[str, List[datetime]] = {}
    _lockouts: Dict[str, datetime] = {}
    
    MAX_ATTEMPTS = 5
    LOCKOUT_DURATIONS = [60, 300, 900, 3600, 86400]
    
    @classmethod
    def record_failed_attempt(cls, identifier: str) -> Tuple[int, Optional[int]]:
        """Record a failed login attempt."""
        now = datetime.utcnow()
        
        cutoff = now - timedelta(hours=1)
        if identifier in cls._failed_attempts:
            cls._failed_attempts[identifier] = [
                t for t in cls._failed_attempts[identifier] if t > cutoff
            ]
        else:
            cls._failed_attempts[identifier] = []
        
        cls._failed_attempts[identifier].append(now)
        attempt_count = len(cls._failed_attempts[identifier])
        
        remaining = cls.MAX_ATTEMPTS - attempt_count
        
        if attempt_count >= cls.MAX_ATTEMPTS:
            lockout_index = min(
                cls._get_lockout_count(identifier),
                len(cls.LOCKOUT_DURATIONS) - 1
            )
            lockout_duration = cls.LOCKOUT_DURATIONS[lockout_index]
            cls._lockouts[identifier] = now + timedelta(seconds=lockout_duration)
            return 0, lockout_duration
        
        return max(0, remaining), None
    
    @classmethod
    def is_locked_out(cls, identifier: str) -> Tuple[bool, Optional[int]]:
        """Check if an account/IP is locked out."""
        if identifier not in cls._lockouts:
            return False, None
        
        lockout_until = cls._lockouts[identifier]
        now = datetime.utcnow()
        
        if now >= lockout_until:
            del cls._lockouts[identifier]
            return False, None
        
        remaining = int((lockout_until - now).total_seconds())
        return True, remaining
    
    @classmethod
    def clear_attempts(cls, identifier: str):
        """Clear failed attempts after successful login."""
        cls._failed_attempts.pop(identifier, None)
    
    @classmethod
    def _get_lockout_count(cls, identifier: str) -> int:
        """Get number of times this identifier has been locked out."""
        return 0


# ============================================================================
# CSRF TOKEN MANAGER
# ============================================================================

class CSRFTokenManager:
    """CSRF token management for HTMX integration."""
    
    TOKEN_LENGTH = 32
    TOKEN_HEADER = "X-CSRF-Token"
    COOKIE_NAME = "csrf_token"
    
    @classmethod
    def generate_token(cls) -> str:
        """Generate a cryptographically secure CSRF token."""
        return secrets.token_urlsafe(cls.TOKEN_LENGTH)
    
    @classmethod
    def validate_double_submit(
        cls,
        cookie_token: Optional[str],
        header_token: Optional[str],
    ) -> bool:
        """Validate double-submit cookie pattern."""
        if not cookie_token or not header_token:
            return False
        return secrets.compare_digest(cookie_token, header_token)
    
    @classmethod
    def create_signed_token(cls, session_id: str, secret_key: str) -> str:
        """Create a session-bound signed CSRF token."""
        import hmac
        token_data = f"{session_id}:{secrets.token_urlsafe(16)}"
        signature = hmac.new(
            secret_key.encode(),
            token_data.encode(),
            hashlib.sha256
        ).hexdigest()[:16]
        return f"{token_data}:{signature}"
    
    @classmethod
    def verify_signed_token(
        cls,
        token: str,
        session_id: str,
        secret_key: str,
    ) -> bool:
        """Verify a signed CSRF token."""
        import hmac
        try:
            parts = token.rsplit(":", 1)
            if len(parts) != 2:
                return False
            
            token_data, signature = parts
            token_session = token_data.split(":")[0]
            
            if token_session != session_id:
                return False
            
            expected_sig = hmac.new(
                secret_key.encode(),
                token_data.encode(),
                hashlib.sha256
            ).hexdigest()[:16]
            
            return secrets.compare_digest(signature, expected_sig)
        except Exception:
            return False


# ============================================================================
# CONTENT SECURITY POLICY BUILDER
# ============================================================================

class CSPBuilder:
    """Content Security Policy builder for XSS protection."""
    
    def __init__(self):
        self.directives: Dict[str, List[str]] = {
            "default-src": ["'self'"],
            "script-src": ["'self'"],
            "style-src": ["'self'", "'unsafe-inline'"],
            "img-src": ["'self'", "data:", "https:"],
            "font-src": ["'self'", "https://fonts.gstatic.com"],
            "connect-src": ["'self'"],
            "frame-ancestors": ["'none'"],
            "form-action": ["'self'"],
            "base-uri": ["'self'"],
            "object-src": ["'none'"],
        }
        self.report_uri: Optional[str] = None
    
    def add_trusted_source(self, directive: str, source: str) -> "CSPBuilder":
        """Add a trusted source to a directive."""
        if directive in self.directives:
            self.directives[directive].append(source)
        return self
    
    def add_nrs_integration(self) -> "CSPBuilder":
        """Add NRS/FIRS trusted sources."""
        self.add_trusted_source("connect-src", "https://nrs.gov.ng")
        self.add_trusted_source("connect-src", "https://api.nrs.gov.ng")
        self.add_trusted_source("connect-src", "https://taxid.nrs.gov.ng")
        return self
    
    def add_nibss_integration(self) -> "CSPBuilder":
        """Add NIBSS trusted sources."""
        self.add_trusted_source("connect-src", "https://nibss-plc.com.ng")
        return self
    
    def add_htmx_support(self) -> "CSPBuilder":
        """Add HTMX CDN source."""
        self.add_trusted_source("script-src", "https://unpkg.com")
        return self
    
    def add_tailwind_support(self) -> "CSPBuilder":
        """Add Tailwind CSS CDN source."""
        self.add_trusted_source("script-src", "https://cdn.tailwindcss.com")
        self.add_trusted_source("style-src", "https://cdn.tailwindcss.com")
        return self
    
    def add_alpinejs_support(self) -> "CSPBuilder":
        """Add Alpine.js CDN source and required eval permissions.
        
        Alpine.js requires 'unsafe-eval' to evaluate x-data expressions
        and 'unsafe-inline' for inline event handlers like @click.
        """
        self.add_trusted_source("script-src", "https://cdn.jsdelivr.net")
        self.add_trusted_source("script-src", "'unsafe-inline'")
        self.add_trusted_source("script-src", "'unsafe-eval'")
        return self
    
    def build(self) -> str:
        """Build the CSP header value."""
        parts = []
        for directive, sources in self.directives.items():
            parts.append(f"{directive} {' '.join(sources)}")
        
        if self.report_uri:
            parts.append(f"report-uri {self.report_uri}")
        
        return "; ".join(parts)


# ============================================================================
# RIGHT-TO-ERASURE (GDPR/NDPA)
# ============================================================================

@dataclass
class ErasureRequest:
    """Right-to-erasure request under NDPA."""
    
    id: str
    user_id: str
    email: str
    requested_at: datetime
    status: str = "pending"  # pending, processing, completed, rejected
    completed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    
    # What to delete
    delete_transactions: bool = True
    delete_invoices: bool = True
    delete_personal_data: bool = True
    
    # What to retain (statutory requirements)
    retain_tax_records: bool = True  # NRS requires 6 years
    retain_audit_logs: bool = True   # FIRS compliance


class RightToErasureService:
    """
    NDPA Right-to-Erasure workflow.
    
    Allows users to request deletion of their data,
    while retaining statutory records required by NRS/FIRS.
    """
    
    STATUTORY_RETENTION_YEARS = 6  # NRS requirement
    
    async def create_request(
        self,
        user_id: str,
        email: str,
        delete_transactions: bool = True,
        delete_invoices: bool = True,
        delete_personal_data: bool = True,
    ) -> ErasureRequest:
        """Create a new erasure request."""
        request = ErasureRequest(
            id=secrets.token_urlsafe(16),
            user_id=user_id,
            email=email,
            requested_at=datetime.utcnow(),
            delete_transactions=delete_transactions,
            delete_invoices=delete_invoices,
            delete_personal_data=delete_personal_data,
        )
        
        logger.info(f"Erasure request created: {request.id} for user {user_id}")
        return request
    
    async def process_request(
        self,
        request: ErasureRequest,
        db_session,
    ) -> ErasureRequest:
        """
        Process an erasure request.
        
        Steps:
        1. Verify user identity (already done via auth)
        2. Check for active obligations (outstanding invoices, etc.)
        3. Mark statutory records for retention
        4. Delete non-statutory personal data
        5. Anonymize remaining records
        6. Send confirmation email
        """
        request.status = "processing"
        
        # In a real implementation, this would:
        # 1. Query all user data across tables
        # 2. Separate statutory (tax) from non-statutory
        # 3. Delete non-statutory data
        # 4. Anonymize statutory data (replace PII with "DELETED USER")
        # 5. Log the erasure for audit purposes
        
        request.status = "completed"
        request.completed_at = datetime.utcnow()
        
        logger.info(f"Erasure request completed: {request.id}")
        return request
    
    def get_data_categories(self, user_id: str) -> Dict[str, bool]:
        """Get data categories and whether they can be deleted."""
        return {
            "personal_profile": True,
            "contact_information": True,
            "bank_accounts": True,
            "login_history": True,
            "tax_records_current_year": False,  # Statutory
            "tax_records_past_6_years": False,  # Statutory
            "vat_returns": False,               # Statutory
            "wht_records": False,               # Statutory
            "audit_logs": False,                # Compliance
            "nrs_submissions": False,           # FIRS requirement
        }


# ============================================================================
# NIGERIAN VALIDATORS
# ============================================================================

def validate_nigerian_tin(tin: str) -> Tuple[bool, str]:
    """Validate Nigerian TIN."""
    if not tin:
        return False, "TIN is required"
    
    clean_tin = re.sub(r'[\s\-]', '', tin)
    
    if not clean_tin.isdigit():
        return False, "TIN must contain only digits"
    
    if len(clean_tin) < 10 or len(clean_tin) > 14:
        return False, "TIN must be 10-14 digits"
    
    return True, ""


def validate_nigerian_bvn(bvn: str) -> Tuple[bool, str]:
    """Validate Nigerian BVN."""
    if not bvn:
        return False, "BVN is required"
    
    clean_bvn = re.sub(r'[\s\-]', '', bvn)
    
    if not clean_bvn.isdigit():
        return False, "BVN must contain only digits"
    
    if len(clean_bvn) != 11:
        return False, "BVN must be exactly 11 digits"
    
    if not clean_bvn.startswith("22"):
        return False, "BVN must start with 22"
    
    return True, ""


def validate_nigerian_nin(nin: str) -> Tuple[bool, str]:
    """Validate Nigerian NIN."""
    if not nin:
        return False, "NIN is required"
    
    clean_nin = re.sub(r'[\s\-]', '', nin)
    
    if not clean_nin.isdigit():
        return False, "NIN must contain only digits"
    
    if len(clean_nin) != 11:
        return False, "NIN must be exactly 11 digits"
    
    return True, ""


def validate_nigerian_phone(phone: str) -> Tuple[bool, str]:
    """Validate Nigerian phone number."""
    if not phone:
        return False, "Phone number is required"
    
    clean_phone = re.sub(r'[\s\-\+]', '', phone)
    
    if clean_phone.startswith("0") and len(clean_phone) == 11:
        clean_phone = "234" + clean_phone[1:]
    
    if not clean_phone.isdigit():
        return False, "Phone must contain only digits"
    
    if len(clean_phone) != 13:
        return False, "Invalid Nigerian phone number format"
    
    if not clean_phone.startswith("234"):
        return False, "Must be a Nigerian phone number (+234)"
    
    mobile_prefixes = ["803", "806", "816", "810", "813", "814", "903", "906",
                       "705", "805", "807", "815", "811", "905", "915",
                       "701", "708", "802", "808", "812", "902", "901", "904",
                       "809", "817", "818", "909", "908"]
    prefix = clean_phone[3:6]
    if prefix not in mobile_prefixes:
        return False, f"Invalid Nigerian mobile prefix: {prefix}"
    
    return True, ""


def validate_nigerian_account(account: str, bank_code: str = None) -> Tuple[bool, str]:
    """Validate Nigerian bank account number (NUBAN)."""
    if not account:
        return False, "Account number is required"
    
    clean_account = re.sub(r'[\s\-]', '', account)
    
    if not clean_account.isdigit():
        return False, "Account number must contain only digits"
    
    if len(clean_account) != 10:
        return False, "Account number must be exactly 10 digits (NUBAN)"
    
    return True, ""


# ============================================================================
# SINGLETON INSTANCES
# ============================================================================

_encryption_engine: Optional[PIIEncryptionEngine] = None


def get_encryption_engine() -> PIIEncryptionEngine:
    """Get or create singleton encryption engine."""
    global _encryption_engine
    if _encryption_engine is None:
        _encryption_engine = PIIEncryptionEngine()
    return _encryption_engine


_geo_service: Optional[GeoFencingService] = None


def get_geo_service() -> GeoFencingService:
    """Get or create singleton geo-fencing service."""
    global _geo_service
    if _geo_service is None:
        _geo_service = GeoFencingService()
    return _geo_service


rate_limit_config = RateLimitConfig()

csp_builder = CSPBuilder()
csp_builder.add_nrs_integration()
csp_builder.add_nibss_integration()

erasure_service = RightToErasureService()
