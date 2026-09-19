"""
Tekvwa Pro Audit - Report Template Models

Models for customizable report templates per tenant with:
- Custom branding (logo, colors, fonts)
- Column selection and ordering
- Header/footer customization
- Conditional formatting rules
- Multi-language support
"""

import uuid
from datetime import datetime
from typing import Optional, List
from enum import Enum as PyEnum

from sqlalchemy import (
    String, Text, Boolean, Integer, DateTime, ForeignKey,
    Enum, JSON, Float, func
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, AuditMixin


class ReportType(str, PyEnum):
    """Available report types for templates."""
    BALANCE_SHEET = "balance_sheet"
    INCOME_STATEMENT = "income_statement"
    TRIAL_BALANCE = "trial_balance"
    CASH_FLOW = "cash_flow"
    GENERAL_LEDGER = "general_ledger"
    AR_AGING = "ar_aging"
    AP_AGING = "ap_aging"
    BUDGET_VARIANCE = "budget_variance"
    CONSOLIDATED = "consolidated"
    CUSTOM = "custom"


class PageSize(str, PyEnum):
    """Supported page sizes."""
    A4 = "A4"
    LETTER = "letter"
    LEGAL = "legal"
    A3 = "A3"


class PageOrientation(str, PyEnum):
    """Page orientation options."""
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


class FormatRule(str, PyEnum):
    """Conditional formatting rule types."""
    NEGATIVE_RED = "negative_red"              # Show negative values in red
    ZERO_DASH = "zero_dash"                    # Show zero as dash (-)
    THRESHOLD_COLOR = "threshold_color"        # Color based on threshold
    VARIANCE_COLOR = "variance_color"          # Color based on variance %
    SUBTOTAL_BOLD = "subtotal_bold"           # Bold subtotals
    HEADER_HIGHLIGHT = "header_highlight"      # Highlight headers
    ALTERNATING_ROWS = "alternating_rows"      # Zebra striping


class ReportTemplate(BaseModel, AuditMixin):
    """
    Custom report template configuration.
    
    Allows tenants to customize report appearance, columns, and formatting.
    """
    __tablename__ = "report_templates"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Ownership
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="For organization-wide templates shared across entities"
    )
    
    # Template basics
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    report_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Type of report this template applies to"
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_system: Mapped[bool] = mapped_column(
        Boolean, 
        default=False,
        comment="System templates cannot be deleted"
    )
    
    # Branding
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[str] = mapped_column(
        String(7), 
        default="#1a365d",
        comment="Hex color code for headers"
    )
    secondary_color: Mapped[str] = mapped_column(
        String(7), 
        default="#4a5568",
        comment="Hex color code for subheaders"
    )
    accent_color: Mapped[str] = mapped_column(
        String(7), 
        default="#38a169",
        comment="Hex color code for highlights"
    )
    negative_color: Mapped[str] = mapped_column(
        String(7), 
        default="#e53e3e",
        comment="Hex color code for negative values"
    )
    
    # Page settings
    page_size: Mapped[str] = mapped_column(String(10), default="A4")
    orientation: Mapped[str] = mapped_column(String(15), default="portrait")
    margin_top: Mapped[float] = mapped_column(Float, default=20.0, comment="mm")
    margin_bottom: Mapped[float] = mapped_column(Float, default=20.0, comment="mm")
    margin_left: Mapped[float] = mapped_column(Float, default=15.0, comment="mm")
    margin_right: Mapped[float] = mapped_column(Float, default=15.0, comment="mm")
    
    # Header/Footer
    header_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    footer_text: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True,
        comment="Supports placeholders: {page}, {total_pages}, {date}, {company}"
    )
    show_page_numbers: Mapped[bool] = mapped_column(Boolean, default=True)
    show_report_date: Mapped[bool] = mapped_column(Boolean, default=True)
    show_prepared_by: Mapped[bool] = mapped_column(Boolean, default=True)
    show_company_info: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Typography
    title_font_size: Mapped[int] = mapped_column(Integer, default=18)
    header_font_size: Mapped[int] = mapped_column(Integer, default=12)
    body_font_size: Mapped[int] = mapped_column(Integer, default=10)
    font_family: Mapped[str] = mapped_column(String(50), default="Helvetica")
    
    # Number formatting
    decimal_places: Mapped[int] = mapped_column(Integer, default=2)
    thousand_separator: Mapped[str] = mapped_column(String(1), default=",")
    decimal_separator: Mapped[str] = mapped_column(String(1), default=".")
    currency_symbol: Mapped[str] = mapped_column(String(10), default="₦")
    currency_position: Mapped[str] = mapped_column(
        String(10), 
        default="before",
        comment="before or after"
    )
    show_currency_symbol: Mapped[bool] = mapped_column(Boolean, default=True)
    show_zero_as_dash: Mapped[bool] = mapped_column(Boolean, default=False)
    parentheses_for_negative: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Column configuration (JSON for flexibility)
    column_config: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="JSON config for column order, visibility, widths"
    )
    
    # Conditional formatting rules
    format_rules: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="JSON config for conditional formatting"
    )
    
    # Grouping/Sorting preferences
    default_grouping: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Default grouping field"
    )
    default_sort_field: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    default_sort_direction: Mapped[str] = mapped_column(
        String(4),
        default="asc",
        comment="asc or desc"
    )
    
    # Comparative options
    show_comparative: Mapped[bool] = mapped_column(Boolean, default=True)
    comparative_label: Mapped[str] = mapped_column(
        String(50), 
        default="Prior Period"
    )
    show_variance: Mapped[bool] = mapped_column(Boolean, default=True)
    show_variance_percent: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Subtotal options
    show_subtotals: Mapped[bool] = mapped_column(Boolean, default=True)
    show_grand_total: Mapped[bool] = mapped_column(Boolean, default=True)
    subtotal_style: Mapped[str] = mapped_column(
        String(20), 
        default="bold",
        comment="bold, italic, underline, highlight"
    )
    
    # Additional options stored as JSON
    custom_options: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional custom options"
    )
    
    # Multi-language support
    language_code: Mapped[str] = mapped_column(String(5), default="en")
    translations: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Label translations for different languages"
    )
    
    # Usage tracking
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Relationships
    entity = relationship("BusinessEntity", back_populates="report_templates")
    sections = relationship(
        "ReportTemplateSection", 
        back_populates="template",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self):
        return f"<ReportTemplate {self.name} ({self.report_type})>"


class ReportTemplateSection(BaseModel):
    """
    Report section configuration for templates.
    
    Allows customizing individual sections within a report.
    """
    __tablename__ = "report_template_sections"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("report_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Section identity
    section_key: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="e.g., assets, liabilities, revenue, expenses"
    )
    section_title: Mapped[str] = mapped_column(String(100), nullable=False)
    section_order: Mapped[int] = mapped_column(Integer, default=0)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Section styling
    include_header: Mapped[bool] = mapped_column(Boolean, default=True)
    header_background: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
    indent_level: Mapped[int] = mapped_column(Integer, default=0)
    
    # Subtotals
    show_section_total: Mapped[bool] = mapped_column(Boolean, default=True)
    total_label: Mapped[str] = mapped_column(String(100), default="Total")
    
    # Column overrides (JSON)
    column_overrides: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Section-specific column configuration"
    )
    
    # Filter criteria for this section
    filter_criteria: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Filter accounts/items for this section"
    )
    
    # Relationships
    template = relationship("ReportTemplate", back_populates="sections")
    
    def __repr__(self):
        return f"<ReportTemplateSection {self.section_key} ({self.section_order})>"


class ReportGenerationLog(BaseModel):
    """
    Log of report generations for auditing and analytics.
    """
    __tablename__ = "report_generation_logs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Who/What
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("report_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Report info
    report_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    report_format: Mapped[str] = mapped_column(String(10), nullable=False)
    
    # Report parameters
    report_params: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Parameters used to generate the report"
    )
    
    # Timing
    generation_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    generation_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    generation_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Result
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    row_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Download tracking
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    last_downloaded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    def __repr__(self):
        return f"<ReportGenerationLog {self.report_type} {self.report_format}>"
