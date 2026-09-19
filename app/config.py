"""
TekVwarho ProAudit - Configuration Settings

This module handles all application configuration using Pydantic Settings.
Environment variables are loaded from .env file.
"""

from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # ===========================================
    # APPLICATION CONFIGURATION
    # ===========================================
    app_name: str = "TekVwarho ProAudit"
    app_env: str = "development"
    debug: bool = True
    secret_key: str  # Required - must be set in .env
    api_version: str = "v1"
    base_url: str = "http://localhost:5120"  # Base URL for email links
    
    # ===========================================
    # DATABASE CONFIGURATION
    # ===========================================
    database_url: str  # Required - must be set in .env
    database_url_async: Optional[str] = None  # Auto-derived from database_url if not set
    postgres_user: str = "postgres"
    postgres_password: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "tekvwarho_proaudit"
    
    @property
    def async_database_url(self) -> str:
        """Get async database URL, deriving from sync URL if not explicitly set."""
        if self.database_url_async:
            return self.database_url_async
        # Convert postgresql:// to postgresql+asyncpg://
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.database_url
    
    # ===========================================
    # JWT AUTHENTICATION
    # ===========================================
    jwt_secret_key: str  # Required - must be set in .env
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    # ===========================================
    # REDIS CONFIGURATION
    # ===========================================
    redis_url: str = "redis://localhost:6379/0"
    
    # ===========================================
    # NRS/FIRS E-INVOICING API (Federal Inland Revenue Service)
    # Development: https://api-dev.i-fis.com
    # Production: https://atrs-api.firs.gov.ng
    # TIN Verification: https://taxid.nrs.gov.ng/
    # ===========================================
    nrs_api_url: str = "https://api-dev.i-fis.com"
    nrs_api_url_prod: str = "https://atrs-api.firs.gov.ng"
    nrs_api_key: str = ""
    nrs_sandbox_mode: bool = True
    
    # NRS TIN Verification Portal
    nrs_tin_api_url: str = "https://api.taxid.nrs.gov.ng"
    nrs_tin_api_key: str = ""  # May use same key as main NRS API
    
    @property
    def nrs_active_url(self) -> str:
        """Get the active NRS API URL based on sandbox mode."""
        return self.nrs_api_url if self.nrs_sandbox_mode else self.nrs_api_url_prod
    
    # ===========================================
    # OCR SERVICE (Azure Form Recognizer)
    # ===========================================
    azure_form_recognizer_endpoint: str = ""
    azure_form_recognizer_key: str = ""
    
    # ===========================================
    # BANK AGGREGATION APIs (Nigerian Open Banking)
    # ===========================================
    
    # Mono API (https://mono.co) - Nigerian Bank Data Aggregation
    # Used for: Bank statement fetching, account linking, transaction data
    mono_secret_key: str = ""
    mono_public_key: str = ""
    mono_webhook_secret: str = ""
    mono_sandbox_mode: bool = True
    mono_base_url: str = "https://api.withmono.com"
    mono_sandbox_url: str = "https://api.withmono.com"  # Same URL, different keys
    
    @property
    def mono_active_key(self) -> str:
        """Get the active Mono API secret key."""
        return self.mono_secret_key
    
    @property
    def mono_active_url(self) -> str:
        """Get the active Mono API URL."""
        return self.mono_sandbox_url if self.mono_sandbox_mode else self.mono_base_url
    
    # Okra API (https://okra.ng) - Nigerian Open Banking
    # Used for: Bank verification, statements, income, identity
    okra_secret_key: str = ""
    okra_client_token: str = ""
    okra_public_key: str = ""
    okra_webhook_secret: str = ""
    okra_sandbox_mode: bool = True
    okra_base_url: str = "https://api.okra.ng/v2"
    okra_sandbox_url: str = "https://api.okra.ng/v2/sandbox"
    
    @property
    def okra_active_key(self) -> str:
        """Get the active Okra API secret key."""
        return self.okra_secret_key
    
    @property
    def okra_active_url(self) -> str:
        """Get the active Okra API URL."""
        return self.okra_sandbox_url if self.okra_sandbox_mode else self.okra_base_url
    
    # Stitch API (https://stitch.money) - Payment Integration
    # Used for: Payment initiation, account linking, transactions
    stitch_client_id: str = ""
    stitch_client_secret: str = ""
    stitch_webhook_secret: str = ""
    stitch_sandbox_mode: bool = True
    stitch_base_url: str = "https://api.stitch.money"
    stitch_sandbox_url: str = "https://api.stitch.money"  # Same URL, sandbox in credentials
    
    @property
    def stitch_active_url(self) -> str:
        """Get the active Stitch API URL."""
        return self.stitch_sandbox_url if self.stitch_sandbox_mode else self.stitch_base_url
    
    # ===========================================
    # PAYSTACK PAYMENT GATEWAY (https://paystack.com)
    # Used for: Subscription payments, billing, SKU tier upgrades
    # Nigerian Naira (NGN) transactions
    # ===========================================
    paystack_secret_key: str = ""
    paystack_public_key: str = ""
    paystack_webhook_secret: str = ""
    paystack_sandbox_mode: bool = True
    paystack_base_url: str = "https://api.paystack.co"
    
    # Paystack API configuration (#41: Configurable timeout)
    paystack_timeout_seconds: int = 30  # Request timeout in seconds
    paystack_max_retries: int = 3  # Max retry attempts for transient failures (#38)
    
    @property
    def paystack_is_live(self) -> bool:
        """Check if using live Paystack keys (sk_live_*)."""
        return self.paystack_secret_key.startswith("sk_live_")
    
    @property
    def paystack_headers(self) -> dict:
        """Get headers for Paystack API requests."""
        return {
            "Authorization": f"Bearer {self.paystack_secret_key}",
            "Content-Type": "application/json",
        }
    
    # ===========================================
    # DATA RETENTION POLICY (Issue #57)
    # Configure retention periods for billing/usage data
    # ===========================================
    usage_records_retention_days: int = 730  # 2 years for usage_records
    usage_events_retention_days: int = 90  # 90 days for granular usage_events
    payment_transactions_retention_days: int = 2555  # 7 years for payment records (compliance)
    feature_access_logs_retention_days: int = 365  # 1 year for feature access logs
    enable_data_retention_cleanup: bool = True  # Enable automatic cleanup job
    
    # ===========================================
    # FILE STORAGE
    # ===========================================
    storage_backend: str = "local"
    storage_local_path: str = "./uploads"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_s3_bucket: Optional[str] = None

    # Google Cloud Storage (production file storage on GCP)
    gcs_bucket_name: Optional[str] = None
    gcs_project_id: Optional[str] = None
    
    # ===========================================
    # EMAIL CONFIGURATION
    # ===========================================
    mail_server: str = "smtp.office365.com"
    mail_port: int = 587
    mail_use_tls: bool = True
    mail_username: str = ""
    mail_password: str = ""
    mail_from: str = ""
    mail_from_name: str = "TekVwarho ProAudit"
    
    # Support & Billing emails
    support_email: str = "support@tekvwarho.com"
    billing_email: str = "billing@tekvwarho.com"
    
    @property
    def smtp_host(self) -> str:
        """SMTP host server."""
        return self.mail_server
    
    @property
    def smtp_port(self) -> int:
        """SMTP port."""
        return self.mail_port
    
    @property
    def smtp_username(self) -> str:
        """SMTP username."""
        return self.mail_username
    
    @property
    def smtp_password(self) -> str:
        """SMTP password."""
        return self.mail_password
    
    @property
    def smtp_use_tls(self) -> bool:
        """Whether to use TLS for SMTP."""
        return self.mail_use_tls
    
    @property
    def email_from(self) -> str:
        """Email from address."""
        return self.mail_from or self.mail_username
    
    @property
    def email_from_name(self) -> str:
        """Email from display name."""
        return self.mail_from_name
    
    # ===========================================
    # SUPER ADMIN CONFIGURATION
    # These MUST be set via environment variables - no defaults provided for security!
    # The application will fail to start if these are not configured.
    # ===========================================
    super_admin_email: str = ""
    super_admin_password: str = ""
    super_admin_first_name: str = ""
    super_admin_last_name: str = ""
    
    # ===========================================
    # CORS SETTINGS
    # ===========================================
    cors_origins: str = "http://localhost:3000,http://localhost:8000,http://127.0.0.1:8000,http://localhost:5120,http://127.0.0.1:5120"
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins string into list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_env.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.app_env.lower() == "development"


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Uses lru_cache to avoid reading .env file on every call.
    """
    return Settings()


# Export settings instance
settings = get_settings()
