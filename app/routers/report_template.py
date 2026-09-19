"""
Tekvwa Pro Audit - Report Template Router

API endpoints for managing report templates:
- CRUD operations for templates
- Template sections management
- Default template configuration
- Template cloning
"""

import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.report_template_service import ReportTemplateService


router = APIRouter(prefix="/report-templates", tags=["Report Templates"])


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================

class TemplateColorConfig(BaseModel):
    """Color configuration for templates."""
    primary_color: str = Field("#1a365d", pattern="^#[0-9a-fA-F]{6}$")
    secondary_color: str = Field("#4a5568", pattern="^#[0-9a-fA-F]{6}$")
    accent_color: str = Field("#38a169", pattern="^#[0-9a-fA-F]{6}$")
    negative_color: str = Field("#e53e3e", pattern="^#[0-9a-fA-F]{6}$")


class TemplatePageConfig(BaseModel):
    """Page configuration for templates."""
    page_size: str = Field("A4", pattern="^(A4|letter|legal|A3)$")
    orientation: str = Field("portrait", pattern="^(portrait|landscape)$")
    margin_top: float = Field(20.0, ge=5, le=50)
    margin_bottom: float = Field(20.0, ge=5, le=50)
    margin_left: float = Field(15.0, ge=5, le=50)
    margin_right: float = Field(15.0, ge=5, le=50)


class TemplateNumberFormat(BaseModel):
    """Number formatting configuration."""
    decimal_places: int = Field(2, ge=0, le=6)
    thousand_separator: str = Field(",", max_length=1)
    decimal_separator: str = Field(".", max_length=1)
    currency_symbol: str = Field("₦", max_length=10)
    currency_position: str = Field("before", pattern="^(before|after)$")
    show_currency_symbol: bool = True
    show_zero_as_dash: bool = False
    parentheses_for_negative: bool = True


class CreateTemplateRequest(BaseModel):
    """Request to create a new template."""
    name: str = Field(..., min_length=1, max_length=100)
    report_type: str = Field(..., pattern="^(balance_sheet|income_statement|trial_balance|cash_flow|general_ledger|ar_aging|ap_aging|budget_variance|consolidated|custom)$")
    description: Optional[str] = Field(None, max_length=500)
    
    # Branding
    logo_url: Optional[str] = None
    colors: Optional[TemplateColorConfig] = None
    
    # Page
    page: Optional[TemplatePageConfig] = None
    
    # Header/Footer
    header_text: Optional[str] = None
    footer_text: Optional[str] = None
    show_page_numbers: bool = True
    show_report_date: bool = True
    show_prepared_by: bool = True
    show_company_info: bool = True
    
    # Typography
    title_font_size: int = Field(18, ge=10, le=30)
    header_font_size: int = Field(12, ge=8, le=20)
    body_font_size: int = Field(10, ge=6, le=16)
    font_family: str = Field("Helvetica", max_length=50)
    
    # Number formatting
    number_format: Optional[TemplateNumberFormat] = None
    
    # Configuration
    column_config: Optional[Dict[str, Any]] = None
    format_rules: Optional[Dict[str, Any]] = None
    
    # Comparative
    show_comparative: bool = True
    comparative_label: str = "Prior Period"
    show_variance: bool = True
    show_variance_percent: bool = True
    
    # Subtotals
    show_subtotals: bool = True
    show_grand_total: bool = True
    subtotal_style: str = Field("bold", pattern="^(bold|italic|underline|highlight)$")
    
    # Language
    language_code: str = Field("en", max_length=5)


class UpdateTemplateRequest(BaseModel):
    """Request to update a template."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    
    # Branding
    logo_url: Optional[str] = None
    colors: Optional[TemplateColorConfig] = None
    
    # Page
    page: Optional[TemplatePageConfig] = None
    
    # Header/Footer
    header_text: Optional[str] = None
    footer_text: Optional[str] = None
    show_page_numbers: Optional[bool] = None
    show_report_date: Optional[bool] = None
    show_prepared_by: Optional[bool] = None
    show_company_info: Optional[bool] = None
    
    # Typography
    title_font_size: Optional[int] = None
    header_font_size: Optional[int] = None
    body_font_size: Optional[int] = None
    font_family: Optional[str] = None
    
    # Number formatting
    number_format: Optional[TemplateNumberFormat] = None
    
    # Configuration
    column_config: Optional[Dict[str, Any]] = None
    format_rules: Optional[Dict[str, Any]] = None
    
    # Comparative
    show_comparative: Optional[bool] = None
    comparative_label: Optional[str] = None
    show_variance: Optional[bool] = None
    show_variance_percent: Optional[bool] = None
    
    # Subtotals
    show_subtotals: Optional[bool] = None
    show_grand_total: Optional[bool] = None
    subtotal_style: Optional[str] = None
    
    # Custom options
    custom_options: Optional[Dict[str, Any]] = None


class CreateSectionRequest(BaseModel):
    """Request to create a template section."""
    section_key: str = Field(..., min_length=1, max_length=50)
    section_title: str = Field(..., min_length=1, max_length=100)
    section_order: int = Field(0, ge=0)
    is_visible: bool = True
    include_header: bool = True
    header_background: Optional[str] = None
    indent_level: int = Field(0, ge=0, le=5)
    show_section_total: bool = True
    total_label: str = "Total"
    column_overrides: Optional[Dict[str, Any]] = None
    filter_criteria: Optional[Dict[str, Any]] = None


class UpdateSectionRequest(BaseModel):
    """Request to update a template section."""
    section_title: Optional[str] = None
    section_order: Optional[int] = None
    is_visible: Optional[bool] = None
    include_header: Optional[bool] = None
    header_background: Optional[str] = None
    indent_level: Optional[int] = None
    show_section_total: Optional[bool] = None
    total_label: Optional[str] = None
    column_overrides: Optional[Dict[str, Any]] = None
    filter_criteria: Optional[Dict[str, Any]] = None


class CloneTemplateRequest(BaseModel):
    """Request to clone a template."""
    new_name: str = Field(..., min_length=1, max_length=100)
    target_entity_id: Optional[str] = None  # If None, clone to same entity


class ReorderSectionsRequest(BaseModel):
    """Request to reorder sections."""
    section_order: List[str] = Field(..., min_items=1)


class TemplateResponse(BaseModel):
    """Response for a template."""
    id: str
    name: str
    report_type: str
    description: Optional[str]
    is_default: bool
    is_active: bool
    is_system: bool
    
    # Branding
    logo_url: Optional[str]
    primary_color: str
    secondary_color: str
    accent_color: str
    negative_color: str
    
    # Page
    page_size: str
    orientation: str
    
    # Usage
    use_count: int
    last_used_at: Optional[datetime]
    
    created_at: datetime
    
    class Config:
        from_attributes = True


class TemplateDetailResponse(TemplateResponse):
    """Detailed response including sections."""
    sections: List[Dict[str, Any]]
    column_config: Optional[Dict[str, Any]]
    format_rules: Optional[Dict[str, Any]]
    number_format: Dict[str, Any]


class SectionResponse(BaseModel):
    """Response for a section."""
    id: str
    section_key: str
    section_title: str
    section_order: int
    is_visible: bool
    include_header: bool
    show_section_total: bool
    total_label: str
    
    class Config:
        from_attributes = True


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("")
async def list_templates(
    entity_id: str = Query(..., description="Entity ID"),
    report_type: Optional[str] = Query(None, description="Filter by report type"),
    active_only: bool = Query(True, description="Only return active templates"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """List all templates available for an entity."""
    service = ReportTemplateService(db)
    
    templates = await service.list_templates(
        entity_id=uuid.UUID(entity_id),
        report_type=report_type,
        active_only=active_only,
        organization_id=current_user.organization_id,
    )
    
    return {
        "templates": [
            {
                "id": str(t.id),
                "name": t.name,
                "report_type": t.report_type,
                "description": t.description,
                "is_default": t.is_default,
                "is_active": t.is_active,
                "is_system": t.is_system,
                "use_count": t.use_count,
                "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
                "created_at": t.created_at.isoformat(),
            }
            for t in templates
        ],
        "count": len(templates),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_template(
    entity_id: str = Query(..., description="Entity ID"),
    request: CreateTemplateRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Create a new report template."""
    service = ReportTemplateService(db)
    
    # Build template kwargs
    kwargs = {}
    
    if request.colors:
        kwargs.update({
            "primary_color": request.colors.primary_color,
            "secondary_color": request.colors.secondary_color,
            "accent_color": request.colors.accent_color,
            "negative_color": request.colors.negative_color,
        })
    
    if request.page:
        kwargs.update({
            "page_size": request.page.page_size,
            "orientation": request.page.orientation,
            "margin_top": request.page.margin_top,
            "margin_bottom": request.page.margin_bottom,
            "margin_left": request.page.margin_left,
            "margin_right": request.page.margin_right,
        })
    
    if request.number_format:
        kwargs.update({
            "decimal_places": request.number_format.decimal_places,
            "thousand_separator": request.number_format.thousand_separator,
            "decimal_separator": request.number_format.decimal_separator,
            "currency_symbol": request.number_format.currency_symbol,
            "currency_position": request.number_format.currency_position,
            "show_currency_symbol": request.number_format.show_currency_symbol,
            "show_zero_as_dash": request.number_format.show_zero_as_dash,
            "parentheses_for_negative": request.number_format.parentheses_for_negative,
        })
    
    kwargs.update({
        "logo_url": request.logo_url,
        "header_text": request.header_text,
        "footer_text": request.footer_text,
        "show_page_numbers": request.show_page_numbers,
        "show_report_date": request.show_report_date,
        "show_prepared_by": request.show_prepared_by,
        "show_company_info": request.show_company_info,
        "title_font_size": request.title_font_size,
        "header_font_size": request.header_font_size,
        "body_font_size": request.body_font_size,
        "font_family": request.font_family,
        "column_config": request.column_config,
        "format_rules": request.format_rules,
        "show_comparative": request.show_comparative,
        "comparative_label": request.comparative_label,
        "show_variance": request.show_variance,
        "show_variance_percent": request.show_variance_percent,
        "show_subtotals": request.show_subtotals,
        "show_grand_total": request.show_grand_total,
        "subtotal_style": request.subtotal_style,
        "language_code": request.language_code,
    })
    
    template = await service.create_template(
        entity_id=uuid.UUID(entity_id),
        name=request.name,
        report_type=request.report_type,
        description=request.description,
        created_by_id=current_user.id,
        **kwargs
    )
    
    await db.commit()
    
    return {
        "success": True,
        "template": {
            "id": str(template.id),
            "name": template.name,
            "report_type": template.report_type,
        }
    }


@router.get("/{template_id}")
async def get_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get a template by ID with sections."""
    service = ReportTemplateService(db)
    
    template = await service.get_template(uuid.UUID(template_id), include_sections=True)
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Get settings for response
    settings = service.get_template_settings(template)
    sections = service.get_section_settings(template)
    
    return {
        "template": {
            "id": str(template.id),
            "name": template.name,
            "report_type": template.report_type,
            "description": template.description,
            "is_default": template.is_default,
            "is_active": template.is_active,
            "is_system": template.is_system,
            "settings": settings,
            "sections": sections,
            "use_count": template.use_count,
            "last_used_at": template.last_used_at.isoformat() if template.last_used_at else None,
            "created_at": template.created_at.isoformat(),
        }
    }


@router.put("/{template_id}")
async def update_template(
    template_id: str,
    request: UpdateTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Update a template."""
    service = ReportTemplateService(db)
    
    # Build updates dict
    updates = {}
    
    if request.name is not None:
        updates["name"] = request.name
    if request.description is not None:
        updates["description"] = request.description
    if request.is_active is not None:
        updates["is_active"] = request.is_active
    if request.logo_url is not None:
        updates["logo_url"] = request.logo_url
    
    if request.colors:
        updates.update({
            "primary_color": request.colors.primary_color,
            "secondary_color": request.colors.secondary_color,
            "accent_color": request.colors.accent_color,
            "negative_color": request.colors.negative_color,
        })
    
    if request.page:
        updates.update({
            "page_size": request.page.page_size,
            "orientation": request.page.orientation,
            "margin_top": request.page.margin_top,
            "margin_bottom": request.page.margin_bottom,
            "margin_left": request.page.margin_left,
            "margin_right": request.page.margin_right,
        })
    
    if request.number_format:
        updates.update({
            "decimal_places": request.number_format.decimal_places,
            "thousand_separator": request.number_format.thousand_separator,
            "decimal_separator": request.number_format.decimal_separator,
            "currency_symbol": request.number_format.currency_symbol,
            "currency_position": request.number_format.currency_position,
            "show_currency_symbol": request.number_format.show_currency_symbol,
            "show_zero_as_dash": request.number_format.show_zero_as_dash,
            "parentheses_for_negative": request.number_format.parentheses_for_negative,
        })
    
    # Add remaining fields
    for field in [
        "header_text", "footer_text", "show_page_numbers", "show_report_date",
        "show_prepared_by", "show_company_info", "title_font_size", "header_font_size",
        "body_font_size", "font_family", "column_config", "format_rules",
        "show_comparative", "comparative_label", "show_variance", "show_variance_percent",
        "show_subtotals", "show_grand_total", "subtotal_style", "custom_options"
    ]:
        value = getattr(request, field, None)
        if value is not None:
            updates[field] = value
    
    try:
        template = await service.update_template(
            uuid.UUID(template_id),
            updated_by_id=current_user.id,
            **updates
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    await db.commit()
    
    return {
        "success": True,
        "template": {
            "id": str(template.id),
            "name": template.name,
        }
    }


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    hard_delete: bool = Query(False, description="Permanently delete"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Delete a template."""
    service = ReportTemplateService(db)
    
    try:
        if hard_delete:
            success = await service.hard_delete_template(uuid.UUID(template_id))
        else:
            success = await service.delete_template(uuid.UUID(template_id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if not success:
        raise HTTPException(status_code=404, detail="Template not found")
    
    await db.commit()
    
    return {"success": True, "deleted": template_id}


@router.post("/{template_id}/set-default")
async def set_default_template(
    template_id: str,
    entity_id: str = Query(..., description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Set a template as the default for its report type."""
    service = ReportTemplateService(db)
    
    # Get template to find report type
    template = await service.get_template(uuid.UUID(template_id), include_sections=False)
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    try:
        template = await service.set_default_template(
            entity_id=uuid.UUID(entity_id),
            template_id=uuid.UUID(template_id),
            report_type=template.report_type
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    await db.commit()
    
    return {
        "success": True,
        "template": {
            "id": str(template.id),
            "name": template.name,
            "is_default": True,
        }
    }


@router.get("/defaults/{report_type}")
async def get_default_template(
    report_type: str,
    entity_id: str = Query(..., description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get the default template for a report type."""
    service = ReportTemplateService(db)
    
    template = await service.get_default_template(
        entity_id=uuid.UUID(entity_id),
        report_type=report_type,
        organization_id=current_user.organization_id,
    )
    
    if not template:
        return {"template": None, "using_default": True}
    
    settings = service.get_template_settings(template)
    
    return {
        "template": {
            "id": str(template.id),
            "name": template.name,
            "is_system": template.is_system,
            "settings": settings,
        },
        "using_default": template.is_system,
    }


@router.post("/{template_id}/clone")
async def clone_template(
    template_id: str,
    entity_id: str = Query(..., description="Source entity ID"),
    request: CloneTemplateRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Clone a template."""
    service = ReportTemplateService(db)
    
    target_entity = uuid.UUID(request.target_entity_id) if request.target_entity_id else uuid.UUID(entity_id)
    
    try:
        new_template = await service.clone_template(
            template_id=uuid.UUID(template_id),
            new_entity_id=target_entity,
            new_name=request.new_name,
            created_by_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    await db.commit()
    
    return {
        "success": True,
        "template": {
            "id": str(new_template.id),
            "name": new_template.name,
            "report_type": new_template.report_type,
        }
    }


# =============================================================================
# SECTION ENDPOINTS
# =============================================================================

@router.get("/{template_id}/sections")
async def list_sections(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """List all sections in a template."""
    service = ReportTemplateService(db)
    
    template = await service.get_template(uuid.UUID(template_id), include_sections=True)
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    sections = service.get_section_settings(template)
    
    return {
        "template_id": template_id,
        "sections": sections,
        "count": len(sections),
    }


@router.post("/{template_id}/sections", status_code=status.HTTP_201_CREATED)
async def add_section(
    template_id: str,
    request: CreateSectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Add a section to a template."""
    service = ReportTemplateService(db)
    
    section = await service.add_section(
        template_id=uuid.UUID(template_id),
        section_key=request.section_key,
        section_title=request.section_title,
        section_order=request.section_order,
        is_visible=request.is_visible,
        include_header=request.include_header,
        header_background=request.header_background,
        indent_level=request.indent_level,
        show_section_total=request.show_section_total,
        total_label=request.total_label,
        column_overrides=request.column_overrides,
        filter_criteria=request.filter_criteria,
    )
    
    await db.commit()
    
    return {
        "success": True,
        "section": {
            "id": str(section.id),
            "section_key": section.section_key,
            "section_title": section.section_title,
        }
    }


@router.put("/{template_id}/sections/{section_id}")
async def update_section(
    template_id: str,
    section_id: str,
    request: UpdateSectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Update a template section."""
    service = ReportTemplateService(db)
    
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    
    section = await service.update_section(uuid.UUID(section_id), **updates)
    
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    
    await db.commit()
    
    return {
        "success": True,
        "section": {
            "id": str(section.id),
            "section_key": section.section_key,
            "section_title": section.section_title,
        }
    }


@router.delete("/{template_id}/sections/{section_id}")
async def delete_section(
    template_id: str,
    section_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Delete a template section."""
    service = ReportTemplateService(db)
    
    success = await service.delete_section(uuid.UUID(section_id))
    
    if not success:
        raise HTTPException(status_code=404, detail="Section not found")
    
    await db.commit()
    
    return {"success": True, "deleted": section_id}


@router.post("/{template_id}/sections/reorder")
async def reorder_sections(
    template_id: str,
    request: ReorderSectionsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Reorder sections in a template."""
    service = ReportTemplateService(db)
    
    section_uuids = [uuid.UUID(s) for s in request.section_order]
    
    sections = await service.reorder_sections(
        template_id=uuid.UUID(template_id),
        section_order=section_uuids
    )
    
    await db.commit()
    
    return {
        "success": True,
        "sections": [
            {
                "id": str(s.id),
                "section_key": s.section_key,
                "section_order": s.section_order,
            }
            for s in sections
        ]
    }


# =============================================================================
# GENERATION HISTORY ENDPOINTS
# =============================================================================

@router.get("/history")
async def get_generation_history(
    entity_id: str = Query(..., description="Entity ID"),
    report_type: Optional[str] = Query(None, description="Filter by report type"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get report generation history."""
    service = ReportTemplateService(db)
    
    logs = await service.get_report_generation_history(
        entity_id=uuid.UUID(entity_id),
        report_type=report_type,
        limit=limit,
    )
    
    return {
        "history": [
            {
                "id": str(log.id),
                "report_type": log.report_type,
                "report_format": log.report_format,
                "success": log.success,
                "generation_time_ms": log.generation_time_ms,
                "file_size_bytes": log.file_size_bytes,
                "row_count": log.row_count,
                "download_count": log.download_count,
                "generated_at": log.generation_started_at.isoformat(),
                "error_message": log.error_message if not log.success else None,
            }
            for log in logs
        ],
        "count": len(logs),
    }
