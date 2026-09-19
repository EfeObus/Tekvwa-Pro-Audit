"""
Tekvwa Pro Audit - Security Utilities

Password hashing, JWT token management, and security helpers.
"""

import secrets
import string
from datetime import datetime, timedelta
from typing import Optional, Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings


# Password hashing context
# Note: bcrypt 4.2+ requires truncate_error=False to avoid errors on passwords
# that could theoretically exceed 72 bytes when encoded
pwd_context = CryptContext(
    schemes=["bcrypt"], 
    deprecated="auto",
    bcrypt__truncate_error=False
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    # bcrypt only uses first 72 bytes - truncate to avoid ValueError in bcrypt 4.2+
    truncated_password = plain_password[:72] if plain_password else plain_password
    return pwd_context.verify(truncated_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password for storing."""
    # bcrypt only uses first 72 bytes - truncate to avoid ValueError in bcrypt 4.2+
    truncated_password = password[:72] if password else password
    return pwd_context.hash(truncated_password)


def generate_random_password(length: int = 12) -> str:
    """
    Generate a secure random password.
    
    Args:
        length: Password length (minimum 8)
    
    Returns:
        A random password with uppercase, lowercase, digits, and special chars
    """
    if length < 8:
        length = 8
    
    # Ensure at least one of each required character type
    password_chars = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*"),
    ]
    
    # Fill the rest with random chars
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password_chars.extend(secrets.choice(alphabet) for _ in range(length - 4))
    
    # Shuffle the password characters
    secrets.SystemRandom().shuffle(password_chars)
    
    return ''.join(password_chars)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Dictionary containing token payload
        expires_delta: Optional custom expiration time
    
    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.access_token_expire_minutes
        )
    
    to_encode.update({"exp": expire, "type": "access"})
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )
    
    return encoded_jwt


def create_refresh_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT refresh token.
    
    Args:
        data: Dictionary containing token payload
        expires_delta: Optional custom expiration time
    
    Returns:
        Encoded JWT refresh token string
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            days=settings.refresh_token_expire_days
        )
    
    to_encode.update({"exp": expire, "type": "refresh"})
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )
    
    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    """
    Decode and verify a JWT token.
    
    Args:
        token: JWT token string
    
    Returns:
        Token payload dict or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError:
        return None


def verify_access_token(token: str) -> Optional[dict]:
    """
    Verify an access token and return payload.
    
    Args:
        token: JWT access token string
    
    Returns:
        Token payload dict or None if invalid
    """
    payload = decode_token(token)
    if payload and payload.get("type") == "access":
        return payload
    return None


def verify_refresh_token(token: str) -> Optional[dict]:
    """
    Verify a refresh token and return payload.
    
    Args:
        token: JWT refresh token string
    
    Returns:
        Token payload dict or None if invalid
    """
    payload = decode_token(token)
    if payload and payload.get("type") == "refresh":
        return payload
    return None


def create_password_reset_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT password reset token.
    
    Args:
        data: Dictionary containing token payload (should have user_id and email)
        expires_delta: Optional custom expiration time (default: 1 hour)
    
    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=1)  # 1 hour expiry
    
    to_encode.update({"exp": expire, "type": "password_reset"})
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )
    
    return encoded_jwt


def verify_password_reset_token(token: str) -> Optional[dict]:
    """
    Verify a password reset token and return payload.
    
    Args:
        token: JWT password reset token string
    
    Returns:
        Token payload dict or None if invalid
    """
    payload = decode_token(token)
    if payload and payload.get("type") == "password_reset":
        return payload
    return None


def create_email_verification_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT email verification token.
    
    Args:
        data: Dictionary containing token payload (should have user_id and email)
        expires_delta: Optional custom expiration time (default: 24 hours)
    
    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=24)  # 24 hour expiry
    
    to_encode.update({"exp": expire, "type": "email_verification"})
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )
    
    return encoded_jwt


def verify_email_verification_token(token: str) -> Optional[dict]:
    """
    Verify an email verification token and return payload.
    
    Args:
        token: JWT email verification token string
    
    Returns:
        Token payload dict or None if invalid
    """
    payload = decode_token(token)
    if payload and payload.get("type") == "email_verification":
        return payload
    return None
