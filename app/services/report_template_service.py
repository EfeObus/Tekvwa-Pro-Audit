"""
Tekvwa Pro Audit - Report Template Service

Service for managing customizable report templates:
- CRUD operations for templates
- Template application to reports
- Default template management
- Template cloning and versioning
"""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from decimal import Decimal

from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.report_template import (
    ReportTemplate,
    ReportTemplateSection,
    ReportGenerationLog,
)
from app.models.entity import BusinessEntity


class ReportTemplateService:
    """Service for managing report templates."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # =========================================================================
    # TEMPLATE CRUD OPERATIONS
    # =========================================================================
    
    async def create_template(
        self,
        entity_id: uuid.UUID,
        name: str,
        report_type: str,
        description: Optional[str] = None,
        organization_id: Optional[uuid.UUID] = None,
        created_by_id: Optional[uuid.UUID] = None,
        **kwargs
    ) -> ReportTemplate:
        """
        Create a new report template.
        
        Args:
            entity_id: The entity this template belongs to
            name: Template name
            report_type: Type of report (balance_sheet, income_statement, etc.)
            description: Optional description
            organization_id: For organization-wide templates
            **kwargs: Additional template properties
        """
        template = ReportTemplate(
            entity_id=entity_id,
            organization_id=organization_id,
            name=name,
            report_type=report_type,
            description=description,
            created_by_id=created_by_id,
            **kwargs
        )
        
        self.db.add(template)
        await self.db.flush()
        
        return template
    
    async def get_template(
        self,
        template_id: uuid.UUID,
        include_sections: bool = True
    ) -> Optional[ReportTemplate]:
        """Get a template by ID with optional section loading."""
        query = select(ReportTemplate).where(ReportTemplate.id == template_id)
        
        if include_sections:
            query = query.options(selectinload(ReportTemplate.sections))
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def list_templates(
        self,
        entity_id: uuid.UUID,
        report_type: Optional[str] = None,
        include_org_templates: bool = True,
        active_only: bool = True,
        organization_id: Optional[uuid.UUID] = None,
    ) -> List[ReportTemplate]:
        """
        List templates available for an entity.
        
        Args:
            entity_id: The entity to list templates for
            report_type: Filter by report type
            include_org_templates: Include organization-wide templates
            active_only: Only return active templates
            organization_id: For including org-wide templates
        """
        conditions = [ReportTemplate.entity_id == entity_id]
        
        # Include org-wide templates if requested
        if include_org_templates and organization_id:
            conditions = [
                or_(
                    ReportTemplate.entity_id == entity_id,
                    ReportTemplate.organization_id == organization_id
                )
            ]
        
        if report_type:
            conditions.append(ReportTemplate.report_type == report_type)
        
        if active_only:
            conditions.append(ReportTemplate.is_active == True)
        
        query = (
            select(ReportTemplate)
            .where(and_(*conditions))
            .order_by(
                ReportTemplate.is_default.desc(),
                ReportTemplate.use_count.desc(),
                ReportTemplate.name
            )
        )
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def update_template(
        self,
        template_id: uuid.UUID,
        updated_by_id: Optional[uuid.UUID] = None,
        **updates
    ) -> Optional[ReportTemplate]:
        """Update a template's properties."""
        template = await self.get_template(template_id, include_sections=False)
        
        if not template:
            return None
        
        if template.is_system:
            # Don't allow modifying system templates
            raise ValueError("Cannot modify system templates")
        
        for key, value in updates.items():
            if hasattr(template, key):
                setattr(template, key, value)
        
        if updated_by_id:
            template.updated_by_id = updated_by_id
        
        await self.db.flush()
        return template
    
    async def delete_template(self, template_id: uuid.UUID) -> bool:
        """Delete a template (soft delete by deactivating)."""
        template = await self.get_template(template_id, include_sections=False)
        
        if not template:
            return False
        
        if template.is_system:
            raise ValueError("Cannot delete system templates")
        
        template.is_active = False
        await self.db.flush()
        return True
    
    async def hard_delete_template(self, template_id: uuid.UUID) -> bool:
        """Permanently delete a template."""
        template = await self.get_template(template_id, include_sections=False)
        
        if not template:
            return False
        
        if template.is_system:
            raise ValueError("Cannot delete system templates")
        
        await self.db.delete(template)
        await self.db.flush()
        return True
    
    # =========================================================================
    # DEFAULT TEMPLATE MANAGEMENT
    # =========================================================================
    
    async def set_default_template(
        self,
        entity_id: uuid.UUID,
        template_id: uuid.UUID,
        report_type: str
    ) -> ReportTemplate:
        """
        Set a template as the default for a report type.
        
        Clears any existing default for the same report type.
        """
        # Clear existing defaults for this report type
        await self.db.execute(
            update(ReportTemplate)
            .where(
                and_(
                    ReportTemplate.entity_id == entity_id,
                    ReportTemplate.report_type == report_type,
                    ReportTemplate.is_default == True
                )
            )
            .values(is_default=False)
        )
        
        # Set new default
        template = await self.get_template(template_id, include_sections=False)
        if not template:
            raise ValueError(f"Template {template_id} not found")
        
        if template.entity_id != entity_id:
            raise ValueError("Template does not belong to this entity")
        
        template.is_default = True
        await self.db.flush()
        
        return template
    
    async def get_default_template(
        self,
        entity_id: uuid.UUID,
        report_type: str,
        organization_id: Optional[uuid.UUID] = None
    ) -> Optional[ReportTemplate]:
        """
        Get the default template for a report type.
        
        Falls back to organization default, then system default.
        """
        # First try entity default
        result = await self.db.execute(
            select(ReportTemplate)
            .where(
                and_(
                    ReportTemplate.entity_id == entity_id,
                    ReportTemplate.report_type == report_type,
                    ReportTemplate.is_default == True,
                    ReportTemplate.is_active == True
                )
            )
            .limit(1)
        )
        template = result.scalar_one_or_none()
        
        if template:
            return template
        
        # Try organization default
        if organization_id:
            result = await self.db.execute(
                select(ReportTemplate)
                .where(
                    and_(
                        ReportTemplate.organization_id == organization_id,
                        ReportTemplate.report_type == report_type,
                        ReportTemplate.is_default == True,
                        ReportTemplate.is_active == True
                    )
                )
                .limit(1)
            )
            template = result.scalar_one_or_none()
            
            if template:
                return template
        
        # Try system default
        result = await self.db.execute(
            select(ReportTemplate)
            .where(
                and_(
                    ReportTemplate.report_type == report_type,
                    ReportTemplate.is_system == True,
                    ReportTemplate.is_default == True,
                    ReportTemplate.is_active == True
                )
            )
            .limit(1)
        )
        
        return result.scalar_one_or_none()
    
    # =========================================================================
    # TEMPLATE SECTIONS
    # =========================================================================
    
    async def add_section(
        self,
        template_id: uuid.UUID,
        section_key: str,
        section_title: str,
        section_order: int = 0,
        **kwargs
    ) -> ReportTemplateSection:
        """Add a section to a template."""
        section = ReportTemplateSection(
            template_id=template_id,
            section_key=section_key,
            section_title=section_title,
            section_order=section_order,
            **kwargs
        )
        
        self.db.add(section)
        await self.db.flush()
        
        return section
    
    async def update_section(
        self,
        section_id: uuid.UUID,
        **updates
    ) -> Optional[ReportTemplateSection]:
        """Update a template section."""
        result = await self.db.execute(
            select(ReportTemplateSection)
            .where(ReportTemplateSection.id == section_id)
        )
        section = result.scalar_one_or_none()
        
        if not section:
            return None
        
        for key, value in updates.items():
            if hasattr(section, key):
                setattr(section, key, value)
        
        await self.db.flush()
        return section
    
    async def delete_section(self, section_id: uuid.UUID) -> bool:
        """Delete a template section."""
        result = await self.db.execute(
            select(ReportTemplateSection)
            .where(ReportTemplateSection.id == section_id)
        )
        section = result.scalar_one_or_none()
        
        if not section:
            return False
        
        await self.db.delete(section)
        await self.db.flush()
        return True
    
    async def reorder_sections(
        self,
        template_id: uuid.UUID,
        section_order: List[uuid.UUID]
    ) -> List[ReportTemplateSection]:
        """Reorder sections in a template."""
        for idx, section_id in enumerate(section_order):
            await self.db.execute(
                update(ReportTemplateSection)
                .where(
                    and_(
                        ReportTemplateSection.id == section_id,
                        ReportTemplateSection.template_id == template_id
                    )
                )
                .values(section_order=idx)
            )
        
        await self.db.flush()
        
        # Return updated sections
        result = await self.db.execute(
            select(ReportTemplateSection)
            .where(ReportTemplateSection.template_id == template_id)
            .order_by(ReportTemplateSection.section_order)
        )
        
        return list(result.scalars().all())
    
    # =========================================================================
    # TEMPLATE CLONING
    # =========================================================================
    
    async def clone_template(
        self,
        template_id: uuid.UUID,
        new_entity_id: uuid.UUID,
        new_name: str,
        created_by_id: Optional[uuid.UUID] = None
    ) -> ReportTemplate:
        """
        Clone a template to a new entity.
        
        Creates a complete copy including all sections.
        """
        original = await self.get_template(template_id, include_sections=True)
        
        if not original:
            raise ValueError(f"Template {template_id} not found")
        
        # Create new template
        new_template = ReportTemplate(
            entity_id=new_entity_id,
            name=new_name,
            description=f"Cloned from: {original.name}",
            report_type=original.report_type,
            is_default=False,
            is_active=True,
            is_system=False,
            # Branding
            logo_url=original.logo_url,
            primary_color=original.primary_color,
            secondary_color=original.secondary_color,
            accent_color=original.accent_color,
            negative_color=original.negative_color,
            # Page settings
            page_size=original.page_size,
            orientation=original.orientation,
            margin_top=original.margin_top,
            margin_bottom=original.margin_bottom,
            margin_left=original.margin_left,
            margin_right=original.margin_right,
            # Header/Footer
            header_text=original.header_text,
            footer_text=original.footer_text,
            show_page_numbers=original.show_page_numbers,
            show_report_date=original.show_report_date,
            show_prepared_by=original.show_prepared_by,
            show_company_info=original.show_company_info,
            # Typography
            title_font_size=original.title_font_size,
            header_font_size=original.header_font_size,
            body_font_size=original.body_font_size,
            font_family=original.font_family,
            # Number formatting
            decimal_places=original.decimal_places,
            thousand_separator=original.thousand_separator,
            decimal_separator=original.decimal_separator,
            currency_symbol=original.currency_symbol,
            currency_position=original.currency_position,
            show_currency_symbol=original.show_currency_symbol,
            show_zero_as_dash=original.show_zero_as_dash,
            parentheses_for_negative=original.parentheses_for_negative,
            # Configuration
            column_config=original.column_config,
            format_rules=original.format_rules,
            default_grouping=original.default_grouping,
            default_sort_field=original.default_sort_field,
            default_sort_direction=original.default_sort_direction,
            # Comparative
            show_comparative=original.show_comparative,
            comparative_label=original.comparative_label,
            show_variance=original.show_variance,
            show_variance_percent=original.show_variance_percent,
            # Subtotals
            show_subtotals=original.show_subtotals,
            show_grand_total=original.show_grand_total,
            subtotal_style=original.subtotal_style,
            # Language
            language_code=original.language_code,
            translations=original.translations,
            custom_options=original.custom_options,
            created_by_id=created_by_id,
        )
        
        self.db.add(new_template)
        await self.db.flush()
        
        # Clone sections
        for section in original.sections:
            new_section = ReportTemplateSection(
                template_id=new_template.id,
                section_key=section.section_key,
                section_title=section.section_title,
                section_order=section.section_order,
                is_visible=section.is_visible,
                include_header=section.include_header,
                header_background=section.header_background,
                indent_level=section.indent_level,
                show_section_total=section.show_section_total,
                total_label=section.total_label,
                column_overrides=section.column_overrides,
                filter_criteria=section.filter_criteria,
            )
            self.db.add(new_section)
        
        await self.db.flush()
        
        return new_template
    
    # =========================================================================
    # TEMPLATE APPLICATION (GET SETTINGS FOR EXPORT)
    # =========================================================================
    
    def get_template_settings(self, template: ReportTemplate) -> Dict[str, Any]:
        """
        Convert a template to settings dict for report generation.
        
        Returns a dict that can be passed to the report export service.
        """
        settings = {
            "template_id": str(template.id),
            "template_name": template.name,
            
            # Branding
            "logo_url": template.logo_url,
            "colors": {
                "primary": template.primary_color,
                "secondary": template.secondary_color,
                "accent": template.accent_color,
                "negative": template.negative_color,
            },
            
            # Page
            "page_size": template.page_size,
            "orientation": template.orientation,
            "margins": {
                "top": template.margin_top,
                "bottom": template.margin_bottom,
                "left": template.margin_left,
                "right": template.margin_right,
            },
            
            # Header/Footer
            "header": {
                "text": template.header_text,
                "show_company_info": template.show_company_info,
            },
            "footer": {
                "text": template.footer_text,
                "show_page_numbers": template.show_page_numbers,
                "show_report_date": template.show_report_date,
                "show_prepared_by": template.show_prepared_by,
            },
            
            # Typography
            "fonts": {
                "family": template.font_family,
                "title_size": template.title_font_size,
                "header_size": template.header_font_size,
                "body_size": template.body_font_size,
            },
            
            # Number formatting
            "number_format": {
                "decimal_places": template.decimal_places,
                "thousand_separator": template.thousand_separator,
                "decimal_separator": template.decimal_separator,
                "currency_symbol": template.currency_symbol,
                "currency_position": template.currency_position,
                "show_currency_symbol": template.show_currency_symbol,
                "show_zero_as_dash": template.show_zero_as_dash,
                "parentheses_for_negative": template.parentheses_for_negative,
            },
            
            # Columns and formatting rules
            "column_config": template.column_config or {},
            "format_rules": template.format_rules or {},
            
            # Sorting/Grouping
            "grouping": template.default_grouping,
            "sort_field": template.default_sort_field,
            "sort_direction": template.default_sort_direction,
            
            # Comparative
            "comparative": {
                "show": template.show_comparative,
                "label": template.comparative_label,
                "show_variance": template.show_variance,
                "show_variance_percent": template.show_variance_percent,
            },
            
            # Subtotals
            "subtotals": {
                "show": template.show_subtotals,
                "show_grand_total": template.show_grand_total,
                "style": template.subtotal_style,
            },
            
            # Language
            "language": template.language_code,
            "translations": template.translations or {},
            
            # Custom
            "custom_options": template.custom_options or {},
        }
        
        return settings
    
    def get_section_settings(
        self, 
        template: ReportTemplate
    ) -> List[Dict[str, Any]]:
        """Get section settings as a list of dicts."""
        sections = []
        
        for section in sorted(template.sections, key=lambda s: s.section_order):
            sections.append({
                "section_key": section.section_key,
                "title": section.section_title,
                "order": section.section_order,
                "visible": section.is_visible,
                "include_header": section.include_header,
                "header_background": section.header_background,
                "indent_level": section.indent_level,
                "show_total": section.show_section_total,
                "total_label": section.total_label,
                "column_overrides": section.column_overrides or {},
                "filter_criteria": section.filter_criteria or {},
            })
        
        return sections
    
    # =========================================================================
    # USAGE TRACKING
    # =========================================================================
    
    async def record_template_use(
        self,
        template_id: uuid.UUID
    ) -> None:
        """Record that a template was used."""
        await self.db.execute(
            update(ReportTemplate)
            .where(ReportTemplate.id == template_id)
            .values(
                use_count=ReportTemplate.use_count + 1,
                last_used_at=datetime.utcnow()
            )
        )
        await self.db.flush()
    
    # =========================================================================
    # REPORT GENERATION LOGGING
    # =========================================================================
    
    async def log_report_generation(
        self,
        entity_id: uuid.UUID,
        report_type: str,
        report_format: str,
        user_id: Optional[uuid.UUID] = None,
        template_id: Optional[uuid.UUID] = None,
        report_params: Optional[Dict[str, Any]] = None,
    ) -> ReportGenerationLog:
        """Start logging a report generation."""
        log = ReportGenerationLog(
            entity_id=entity_id,
            user_id=user_id,
            template_id=template_id,
            report_type=report_type,
            report_format=report_format,
            report_params=report_params,
            generation_started_at=datetime.utcnow(),
        )
        
        self.db.add(log)
        await self.db.flush()
        
        return log
    
    async def complete_report_log(
        self,
        log_id: uuid.UUID,
        success: bool,
        file_size_bytes: Optional[int] = None,
        row_count: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Complete a report generation log entry."""
        result = await self.db.execute(
            select(ReportGenerationLog)
            .where(ReportGenerationLog.id == log_id)
        )
        log = result.scalar_one_or_none()
        
        if log:
            log.generation_completed_at = datetime.utcnow()
            log.success = success
            log.file_size_bytes = file_size_bytes
            log.row_count = row_count
            log.error_message = error_message
            
            if log.generation_started_at:
                delta = log.generation_completed_at - log.generation_started_at
                log.generation_time_ms = int(delta.total_seconds() * 1000)
            
            await self.db.flush()
    
    async def get_report_generation_history(
        self,
        entity_id: uuid.UUID,
        report_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[ReportGenerationLog]:
        """Get report generation history for an entity."""
        conditions = [ReportGenerationLog.entity_id == entity_id]
        
        if report_type:
            conditions.append(ReportGenerationLog.report_type == report_type)
        
        result = await self.db.execute(
            select(ReportGenerationLog)
            .where(and_(*conditions))
            .order_by(ReportGenerationLog.generation_started_at.desc())
            .limit(limit)
        )
        
        return list(result.scalars().all())
    
    # =========================================================================
    # SYSTEM TEMPLATE INITIALIZATION
    # =========================================================================
    
    async def create_system_templates(self) -> List[ReportTemplate]:
        """
        Create default system templates.
        
        Called during system initialization to create base templates.
        """
        templates = []
        
        # Balance Sheet template
        bs_template = await self._create_system_balance_sheet_template()
        templates.append(bs_template)
        
        # Income Statement template
        is_template = await self._create_system_income_statement_template()
        templates.append(is_template)
        
        # Trial Balance template
        tb_template = await self._create_system_trial_balance_template()
        templates.append(tb_template)
        
        await self.db.flush()
        
        return templates
    
    async def _create_system_balance_sheet_template(self) -> ReportTemplate:
        """Create system Balance Sheet template."""
        template = ReportTemplate(
            entity_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),  # System
            name="Standard Balance Sheet",
            description="IFRS-compliant Balance Sheet template",
            report_type="balance_sheet",
            is_default=True,
            is_system=True,
            is_active=True,
            column_config={
                "columns": [
                    {"key": "account_code", "label": "Code", "width": 60, "visible": True},
                    {"key": "account_name", "label": "Account", "width": 200, "visible": True},
                    {"key": "current", "label": "Current Period", "width": 100, "visible": True, "align": "right"},
                    {"key": "prior", "label": "Prior Period", "width": 100, "visible": True, "align": "right"},
                    {"key": "variance", "label": "Variance", "width": 80, "visible": True, "align": "right"},
                    {"key": "variance_pct", "label": "%", "width": 50, "visible": True, "align": "right"},
                ]
            },
            format_rules={
                "rules": [
                    {"type": "negative_red", "columns": ["current", "prior", "variance"]},
                    {"type": "subtotal_bold", "sections": ["total_assets", "total_liabilities", "total_equity"]},
                ]
            },
        )
        
        self.db.add(template)
        await self.db.flush()
        
        # Add sections
        sections = [
            ("assets", "ASSETS", 1),
            ("current_assets", "Current Assets", 2),
            ("non_current_assets", "Non-Current Assets", 3),
            ("total_assets", "TOTAL ASSETS", 4),
            ("liabilities", "LIABILITIES", 5),
            ("current_liabilities", "Current Liabilities", 6),
            ("non_current_liabilities", "Non-Current Liabilities", 7),
            ("total_liabilities", "TOTAL LIABILITIES", 8),
            ("equity", "EQUITY", 9),
            ("total_equity", "TOTAL EQUITY", 10),
        ]
        
        for key, title, order in sections:
            section = ReportTemplateSection(
                template_id=template.id,
                section_key=key,
                section_title=title,
                section_order=order,
                show_section_total=key.startswith("total_"),
            )
            self.db.add(section)
        
        return template
    
    async def _create_system_income_statement_template(self) -> ReportTemplate:
        """Create system Income Statement template."""
        template = ReportTemplate(
            entity_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            name="Standard Income Statement",
            description="IFRS-compliant Income Statement (P&L) template",
            report_type="income_statement",
            is_default=True,
            is_system=True,
            is_active=True,
            column_config={
                "columns": [
                    {"key": "account_code", "label": "Code", "width": 60, "visible": True},
                    {"key": "account_name", "label": "Description", "width": 200, "visible": True},
                    {"key": "current", "label": "Current Period", "width": 100, "visible": True, "align": "right"},
                    {"key": "ytd", "label": "YTD", "width": 100, "visible": True, "align": "right"},
                    {"key": "budget", "label": "Budget", "width": 100, "visible": False, "align": "right"},
                    {"key": "variance", "label": "Variance", "width": 80, "visible": True, "align": "right"},
                ]
            },
        )
        
        self.db.add(template)
        await self.db.flush()
        
        # Add sections
        sections = [
            ("revenue", "REVENUE", 1),
            ("cost_of_sales", "COST OF SALES", 2),
            ("gross_profit", "GROSS PROFIT", 3),
            ("operating_expenses", "OPERATING EXPENSES", 4),
            ("operating_income", "OPERATING INCOME", 5),
            ("other_income", "OTHER INCOME", 6),
            ("other_expenses", "OTHER EXPENSES", 7),
            ("profit_before_tax", "PROFIT BEFORE TAX", 8),
            ("income_tax", "INCOME TAX", 9),
            ("net_profit", "NET PROFIT", 10),
        ]
        
        for key, title, order in sections:
            section = ReportTemplateSection(
                template_id=template.id,
                section_key=key,
                section_title=title,
                section_order=order,
            )
            self.db.add(section)
        
        return template
    
    async def _create_system_trial_balance_template(self) -> ReportTemplate:
        """Create system Trial Balance template."""
        template = ReportTemplate(
            entity_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            name="Standard Trial Balance",
            description="Standard Trial Balance with debit/credit columns",
            report_type="trial_balance",
            is_default=True,
            is_system=True,
            is_active=True,
            column_config={
                "columns": [
                    {"key": "account_code", "label": "Account Code", "width": 80, "visible": True},
                    {"key": "account_name", "label": "Account Name", "width": 200, "visible": True},
                    {"key": "account_type", "label": "Type", "width": 80, "visible": True},
                    {"key": "debit", "label": "Debit", "width": 100, "visible": True, "align": "right"},
                    {"key": "credit", "label": "Credit", "width": 100, "visible": True, "align": "right"},
                ]
            },
        )
        
        self.db.add(template)
        
        return template
