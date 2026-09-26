"""
Fixed Assets Router - API endpoints for Fixed Asset Register.

2026 Nigeria Tax Reform Compliance:
- Fixed assets tracked for depreciation and capital gains
- Capital gains on disposal taxed at CIT rate
- VAT recovery on qualifying capital assets via IRN
- Integration with Development Levy threshold calculation

SKU Tier: PROFESSIONAL (₦150,000+/mo)
Feature Flag: FIXED_ASSETS

Author: Tekvwa Pro Audit
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import (
    get_current_active_user,
    require_organization_permission,
    record_usage_event,
    require_feature,
    require_entity_access,
)
from app.models.user import User, UserRole
from app.models.entity import BusinessEntity
from app.models.sku import Feature, UsageMetricType
from app.utils.permissions import OrganizationPermission
from app.models.fixed_asset import (
    AssetCategory,
    AssetStatus,
    DepreciationMethod,
    DisposalType,
)
from app.services.fixed_asset_service import FixedAssetService
from app.services.audit_service import AuditService
from app.models.audit_consolidated import AuditAction

router = APIRouter(
    prefix="/api/v1/fixed-assets", 
    tags=["Fixed Assets"],
    dependencies=[Depends(require_feature([Feature.FIXED_ASSETS]))]
)

# Note: All endpoints in this router require Professional tier (FIXED_ASSETS feature)


# ===========================================
# PYDANTIC SCHEMAS
# ===========================================

class FixedAssetCreate(BaseModel):
    """Schema for creating a new fixed asset."""
    entity_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: AssetCategory
    
    # Acquisition details
    acquisition_date: date
    acquisition_cost: Decimal = Field(..., ge=0)
    vendor_name: Optional[str] = None
    vendor_irn: Optional[str] = Field(None, description="Invoice Reference Number for VAT recovery")
    invoice_number: Optional[str] = None
    
    # Depreciation settings
    depreciation_method: DepreciationMethod = DepreciationMethod.STRAIGHT_LINE
    useful_life_years: Optional[int] = Field(None, ge=1, le=100)
    depreciation_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    residual_value: Decimal = Field(default=Decimal("0"), ge=0)
    
    # Physical details
    serial_number: Optional[str] = None
    location: Optional[str] = None
    condition: Optional[str] = None
    
    # Insurance
    is_insured: bool = False
    insurance_policy_number: Optional[str] = None
    insurance_value: Optional[Decimal] = Field(None, ge=0)
    insurance_expiry_date: Optional[date] = None

    class Config:
        json_encoders = {
            Decimal: str,
        }


class FixedAssetUpdate(BaseModel):
    """Schema for updating a fixed asset."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[AssetCategory] = None
    status: Optional[AssetStatus] = None
    
    # Physical details
    serial_number: Optional[str] = None
    location: Optional[str] = None
    condition: Optional[str] = None
    
    # Insurance
    is_insured: Optional[bool] = None
    insurance_policy_number: Optional[str] = None
    insurance_value: Optional[Decimal] = Field(None, ge=0)
    insurance_expiry_date: Optional[date] = None

    class Config:
        json_encoders = {
            Decimal: str,
        }


class AssetDisposalRequest(BaseModel):
    """Schema for disposing of an asset."""
    disposal_type: DisposalType
    disposal_date: date
    disposal_proceeds: Decimal = Field(default=Decimal("0"), ge=0)
    buyer_name: Optional[str] = None
    buyer_tin: Optional[str] = None
    notes: Optional[str] = None


class AssetRevaluationRequest(BaseModel):
    """Schema for revaluing an asset."""
    revaluation_date: date
    new_value: Decimal = Field(..., gt=0, description="New fair market value")
    reason: str = Field(..., min_length=1, max_length=500, description="Reason for revaluation")
    valuer_name: Optional[str] = Field(None, description="Name of valuer/appraiser")
    valuer_reference: Optional[str] = Field(None, description="Valuation report reference")
    adjust_depreciation: bool = Field(default=True, description="Adjust future depreciation based on new value")


class AssetRevaluationResponse(BaseModel):
    """Response schema for asset revaluation."""
    asset_id: UUID
    asset_name: str
    previous_book_value: Decimal
    new_book_value: Decimal
    revaluation_surplus_deficit: Decimal
    revaluation_date: date
    reason: str
    valuer_name: Optional[str]
    message: str

    class Config:
        json_encoders = {Decimal: str}


class AssetTransferRequest(BaseModel):
    """Schema for transferring an asset."""
    transfer_date: date
    to_entity_id: Optional[UUID] = Field(None, description="Transfer to different entity")
    new_location: Optional[str] = Field(None, description="New physical location")
    reason: str = Field(..., min_length=1, max_length=500, description="Reason for transfer")
    notes: Optional[str] = None


class AssetTransferResponse(BaseModel):
    """Response schema for asset transfer."""
    asset_id: UUID
    asset_name: str
    transfer_date: date
    from_entity_id: UUID
    to_entity_id: UUID
    from_location: Optional[str]
    to_location: Optional[str]
    reason: str
    message: str


class DepreciationEntryResponse(BaseModel):
    """Response schema for depreciation history entry."""
    id: UUID
    period_start: date
    period_end: date
    depreciation_amount: Decimal
    opening_nbv: Decimal
    closing_nbv: Decimal
    method: str
    created_at: str

    class Config:
        from_attributes = True
        json_encoders = {Decimal: str}


class DepreciationHistoryResponse(BaseModel):
    """Response schema for full depreciation history."""
    asset_id: UUID
    asset_name: str
    acquisition_cost: Decimal
    accumulated_depreciation: Decimal
    current_nbv: Decimal
    entries: List[DepreciationEntryResponse]
    total_entries: int

    class Config:
        json_encoders = {Decimal: str}


class DepreciationRunRequest(BaseModel):
    """Schema for running depreciation."""
    entity_id: UUID
    fiscal_year_end: date
    period_start: date
    period_end: date


class FixedAssetResponse(BaseModel):
    """Response schema for fixed asset."""
    id: UUID
    entity_id: UUID
    name: str
    description: Optional[str]
    asset_code: str
    category: str
    status: str
    
    acquisition_date: date
    acquisition_cost: Decimal
    vendor_name: Optional[str]
    vendor_irn: Optional[str]
    
    depreciation_method: str
    useful_life_years: Optional[int]
    depreciation_rate: Decimal
    residual_value: Decimal
    accumulated_depreciation: Decimal
    net_book_value: Decimal
    is_fully_depreciated: bool
    
    location: Optional[str]
    is_insured: bool  # Derived from insured_value
    insured_value: Optional[Decimal]
    insurance_policy_number: Optional[str]
    
    created_at: str
    updated_at: Optional[str]

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: str,
        }


# ===========================================
# CRUD ENDPOINTS
# ===========================================

@router.post(
    "/",
    response_model=FixedAssetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new fixed asset",
)
async def create_fixed_asset(
    asset_data: FixedAssetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_organization_permission([OrganizationPermission.CREATE_TRANSACTIONS])
    ),
):
    """
    Create a new fixed asset in the register.
    
    Required for 2026 compliance:
    - Track acquisition cost for depreciation
    - Capture vendor IRN for VAT recovery on capital assets
    - Auto-generate asset code for tracking
    """
    service = FixedAssetService(db)
    
    try:
        asset = await service.create_asset(
            entity_id=asset_data.entity_id,
            name=asset_data.name,
            category=asset_data.category,
            acquisition_date=asset_data.acquisition_date,
            acquisition_cost=asset_data.acquisition_cost,
            depreciation_method=asset_data.depreciation_method,
            useful_life_years=asset_data.useful_life_years,
            depreciation_rate=asset_data.depreciation_rate,
            residual_value=asset_data.residual_value,
            vendor_name=asset_data.vendor_name,
            vendor_irn=asset_data.vendor_irn,
            invoice_number=asset_data.invoice_number,
            description=asset_data.description,
            serial_number=asset_data.serial_number,
            location=asset_data.location,
            condition=asset_data.condition,
            is_insured=asset_data.is_insured,
            insurance_policy_number=asset_data.insurance_policy_number,
            insurance_value=asset_data.insurance_value,
            insurance_expiry_date=asset_data.insurance_expiry_date,
            created_by_id=current_user.id,
        )
        
        # Audit logging
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=asset_data.entity_id,
            entity_type="fixed_asset",
            entity_id=str(asset.id),
            action=AuditAction.CREATE,
            user_id=current_user.id,
            new_values={
                "name": asset.name,
                "category": asset.category.value if hasattr(asset.category, 'value') else str(asset.category),
                "acquisition_cost": str(asset.acquisition_cost),
                "acquisition_date": str(asset.acquisition_date),
            }
        )
        
        # Record usage metering for transaction tracking
        if current_user.organization_id:
            await record_usage_event(
                db=db,
                organization_id=current_user.organization_id,
                metric_type=UsageMetricType.TRANSACTIONS,
                entity_id=asset_data.entity_id,
                user_id=current_user.id,
                resource_type="fixed_asset",
                resource_id=str(asset.id),
            )
        
        return _asset_to_response(asset)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/entity/{entity_id}",
    response_model=List[FixedAssetResponse],
    summary="Get all fixed assets for an entity",
)
async def get_entity_assets(
    entity_id: UUID,
    _entity_access: BusinessEntity = Depends(require_entity_access),
    status: Optional[AssetStatus] = Query(None, description="Filter by status"),
    category: Optional[AssetCategory] = Query(None, description="Filter by category"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get all fixed assets for a specific entity."""
    service = FixedAssetService(db)
    
    assets, total = await service.get_assets_for_entity(
        entity_id=entity_id,
        status=status,
        category=category,
    )
    
    return [_asset_to_response(asset) for asset in assets]


@router.get(
    "/{asset_id}",
    response_model=FixedAssetResponse,
    summary="Get a specific fixed asset",
)
async def get_fixed_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get details of a specific fixed asset."""
    service = FixedAssetService(db)
    
    asset = await service.get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    return _asset_to_response(asset)


@router.patch(
    "/{asset_id}",
    response_model=FixedAssetResponse,
    summary="Update a fixed asset",
)
async def update_fixed_asset(
    asset_id: UUID,
    asset_data: FixedAssetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_organization_permission([OrganizationPermission.CREATE_TRANSACTIONS])
    ),
):
    """Update a fixed asset's details."""
    service = FixedAssetService(db)
    
    asset = await service.get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Capture old values for audit
    old_values = {
        "name": asset.name,
        "category": asset.category.value if hasattr(asset.category, 'value') else str(asset.category),
        "status": asset.status.value if hasattr(asset.status, 'value') else str(asset.status),
        "location": asset.location,
    }
    
    # Build update dict from provided fields
    update_dict = asset_data.model_dump(exclude_unset=True)
    
    try:
        updated_asset = await service.update_asset(
            asset_id=asset_id,
            updated_by_id=current_user.id,
            **update_dict,
        )
        
        # Audit logging
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=asset.entity_id,
            entity_type="fixed_asset",
            entity_id=str(asset_id),
            action=AuditAction.UPDATE,
            user_id=current_user.id,
            old_values=old_values,
            new_values=update_dict,
        )
        
        return _asset_to_response(updated_asset)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ===========================================
# DEPRECIATION ENDPOINTS
# ===========================================

@router.post(
    "/depreciation/run",
    summary="Run depreciation for all active assets",
)
async def run_depreciation(
    request: DepreciationRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_organization_permission([OrganizationPermission.CREATE_TRANSACTIONS])
    ),
):
    """
    Run depreciation posting for all active assets in an entity.
    
    This should be run at the end of each fiscal period (monthly/annually).
    Creates depreciation entries and updates accumulated depreciation.
    """
    service = FixedAssetService(db)
    
    try:
        entries = await service.run_depreciation(
            entity_id=request.entity_id,
            fiscal_year_end=request.fiscal_year_end,
            period_start=request.period_start,
            period_end=request.period_end,
            created_by_id=current_user.id,
        )
        
        return {
            "message": f"Depreciation posted for {len(entries)} assets",
            "entries_created": len(entries),
            "period": f"{request.period_start} to {request.period_end}",
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/entity/{entity_id}/depreciation-schedule",
    summary="Get depreciation schedule for fiscal year",
)
async def get_depreciation_schedule(
    entity_id: UUID,
    _entity_access: BusinessEntity = Depends(require_entity_access),
    fiscal_year_end: date = Query(..., description="Fiscal year end date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get depreciation schedule for all assets in an entity for a fiscal year.
    
    Shows opening balance, depreciation amount, and closing balance for each asset.
    """
    service = FixedAssetService(db)
    
    schedule = await service.get_depreciation_schedule(
        entity_id=entity_id,
        fiscal_year_end=fiscal_year_end,
    )
    
    return schedule


# ===========================================
# DISPOSAL ENDPOINTS
# ===========================================

@router.post(
    "/{asset_id}/dispose",
    summary="Dispose of a fixed asset",
)
async def dispose_asset(
    asset_id: UUID,
    disposal: AssetDisposalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_organization_permission([OrganizationPermission.CREATE_TRANSACTIONS])
    ),
):
    """
    Dispose of a fixed asset.
    
    2026 Compliance:
    - Capital gains on disposal are taxed at CIT rate
    - Must capture buyer details for audit trail
    - Proceeds are compared to net book value for gain/loss
    """
    service = FixedAssetService(db)
    
    asset = await service.get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if asset.status == AssetStatus.DISPOSED:
        raise HTTPException(status_code=400, detail="Asset already disposed")
    
    try:
        disposed_asset, capital_gain = await service.dispose_asset(
            asset_id=asset_id,
            disposal_type=disposal.disposal_type,
            disposal_date=disposal.disposal_date,
            disposal_proceeds=disposal.disposal_proceeds,
            buyer_name=disposal.buyer_name,
            buyer_tin=disposal.buyer_tin,
            notes=disposal.notes,
            disposed_by_id=current_user.id,
        )
        
        # Audit logging
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=asset.entity_id,
            entity_type="fixed_asset",
            entity_id=str(asset_id),
            action=AuditAction.UPDATE,
            user_id=current_user.id,
            old_values={"status": "active"},
            new_values={
                "status": "disposed",
                "disposal_type": disposal.disposal_type.value,
                "disposal_date": str(disposal.disposal_date),
                "disposal_proceeds": str(disposal.disposal_proceeds),
                "capital_gain_loss": str(capital_gain),
            }
        )
        
        return {
            "message": "Asset disposed successfully",
            "asset_id": str(disposed_asset.id),
            "asset_name": disposed_asset.name,
            "disposal_type": disposal.disposal_type.value,
            "disposal_proceeds": str(disposal.disposal_proceeds),
            "net_book_value_at_disposal": str(disposed_asset.net_book_value),
            "capital_gain_loss": str(capital_gain),
            "tax_note": "Capital gains taxed at CIT rate under 2026 reform" if capital_gain > 0 else None,
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ===========================================
# REPORTING ENDPOINTS
# ===========================================

@router.get(
    "/entity/{entity_id}/summary",
    summary="Get asset register summary",
)
async def get_asset_register_summary(
    entity_id: UUID,
    _entity_access: BusinessEntity = Depends(require_entity_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get summary of the fixed asset register.
    
    Returns totals by category, total values, and VAT recovery status.
    """
    service = FixedAssetService(db)
    
    summary = await service.get_asset_register_summary(entity_id)
    
    return summary


@router.get(
    "/entity/{entity_id}/capital-gains",
    summary="Get capital gains report for disposed assets",
)
async def get_capital_gains_report(
    entity_id: UUID,
    _entity_access: BusinessEntity = Depends(require_entity_access),
    start_date: date = Query(..., description="Report start date"),
    end_date: date = Query(..., description="Report end date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get capital gains report for disposed assets within a date range.
    
    2026 Compliance:
    - Capital gains are now taxed at CIT rate (not separate CGT)
    - Report shows all disposals with gains/losses
    - Total taxable gain for CIT calculation
    """
    service = FixedAssetService(db)
    
    report = await service.get_capital_gains_report(
        entity_id=entity_id,
        start_date=start_date,
        end_date=end_date,
    )
    
    return report


# ===========================================
# ASSET MANAGEMENT ENDPOINTS
# ===========================================

@router.delete(
    "/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete/archive a fixed asset",
)
async def delete_fixed_asset(
    asset_id: UUID,
    permanent: bool = Query(False, description="Permanently delete instead of archive"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_organization_permission([OrganizationPermission.CREATE_TRANSACTIONS])
    ),
):
    """
    Delete or archive a fixed asset.
    
    By default, assets are soft-deleted (archived) to maintain audit trail.
    Permanent deletion requires elevated permissions and should be used cautiously.
    
    Note: Disposed assets cannot be deleted - they must remain for tax records.
    """
    service = FixedAssetService(db)
    
    asset = await service.get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if asset.status == AssetStatus.DISPOSED:
        raise HTTPException(
            status_code=400, 
            detail="Cannot delete disposed assets - required for tax records"
        )
    
    try:
        if permanent:
            # Check for admin role for permanent deletion
            if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
                raise HTTPException(
                    status_code=403,
                    detail="Permanent deletion requires admin privileges"
                )
            await service.permanent_delete_asset(asset_id)
            
            # Audit logging for permanent delete
            audit_service = AuditService(db)
            await audit_service.log_action(
                business_entity_id=asset.entity_id,
                entity_type="fixed_asset",
                entity_id=str(asset_id),
                action=AuditAction.DELETE,
                user_id=current_user.id,
                old_values={"name": asset.name, "status": "permanent_delete"},
            )
        else:
            await service.archive_asset(asset_id, archived_by_id=current_user.id)
            
            # Audit logging for archive
            audit_service = AuditService(db)
            await audit_service.log_action(
                business_entity_id=asset.entity_id,
                entity_type="fixed_asset",
                entity_id=str(asset_id),
                action=AuditAction.UPDATE,
                user_id=current_user.id,
                old_values={"status": "active"},
                new_values={"status": "archived"},
            )
        
        return None
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{asset_id}/revalue",
    response_model=AssetRevaluationResponse,
    summary="Revalue a fixed asset",
)
async def revalue_asset(
    asset_id: UUID,
    revaluation: AssetRevaluationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_organization_permission([OrganizationPermission.CREATE_TRANSACTIONS])
    ),
):
    """
    Revalue a fixed asset to fair market value.
    
    2026 Compliance:
    - Revaluation surplus goes to revaluation reserve (equity)
    - Revaluation deficit reduces reserve, then goes to P&L
    - Must maintain revaluation history for audit
    - Affects future depreciation if adjust_depreciation is True
    """
    service = FixedAssetService(db)
    
    asset = await service.get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if asset.status == AssetStatus.DISPOSED:
        raise HTTPException(status_code=400, detail="Cannot revalue disposed asset")
    
    if asset.status == AssetStatus.ARCHIVED:
        raise HTTPException(status_code=400, detail="Cannot revalue archived asset")
    
    previous_nbv = asset.net_book_value
    
    try:
        updated_asset = await service.revalue_asset(
            asset_id=asset_id,
            new_value=revaluation.new_value,
            revaluation_date=revaluation.revaluation_date,
            reason=revaluation.reason,
            valuer_name=revaluation.valuer_name,
            valuer_reference=revaluation.valuer_reference,
            adjust_depreciation=revaluation.adjust_depreciation,
            revalued_by_id=current_user.id,
        )
        
        surplus_deficit = revaluation.new_value - previous_nbv
        
        return AssetRevaluationResponse(
            asset_id=updated_asset.id,
            asset_name=updated_asset.name,
            previous_book_value=previous_nbv,
            new_book_value=updated_asset.net_book_value,
            revaluation_surplus_deficit=surplus_deficit,
            revaluation_date=revaluation.revaluation_date,
            reason=revaluation.reason,
            valuer_name=revaluation.valuer_name,
            message=f"Asset revalued successfully. {'Surplus' if surplus_deficit >= 0 else 'Deficit'} of {abs(surplus_deficit)} recorded.",
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{asset_id}/transfer",
    response_model=AssetTransferResponse,
    summary="Transfer a fixed asset",
)
async def transfer_asset(
    asset_id: UUID,
    transfer: AssetTransferRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_organization_permission([OrganizationPermission.CREATE_TRANSACTIONS])
    ),
):
    """
    Transfer a fixed asset to a different entity or location.
    
    Supports:
    - Inter-entity transfers (within the same organization)
    - Location changes (physical relocation)
    - Combined entity and location transfers
    
    Note: At least one of to_entity_id or new_location must be provided.
    """
    service = FixedAssetService(db)
    
    asset = await service.get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if asset.status == AssetStatus.DISPOSED:
        raise HTTPException(status_code=400, detail="Cannot transfer disposed asset")
    
    if not transfer.to_entity_id and not transfer.new_location:
        raise HTTPException(
            status_code=400, 
            detail="Must provide either to_entity_id or new_location for transfer"
        )
    
    from_entity_id = asset.entity_id
    from_location = asset.location
    to_entity_id = transfer.to_entity_id or from_entity_id
    to_location = transfer.new_location or from_location
    
    try:
        updated_asset = await service.transfer_asset(
            asset_id=asset_id,
            to_entity_id=to_entity_id,
            new_location=to_location,
            transfer_date=transfer.transfer_date,
            reason=transfer.reason,
            notes=transfer.notes,
            transferred_by_id=current_user.id,
        )
        
        return AssetTransferResponse(
            asset_id=updated_asset.id,
            asset_name=updated_asset.name,
            transfer_date=transfer.transfer_date,
            from_entity_id=from_entity_id,
            to_entity_id=to_entity_id,
            from_location=from_location,
            to_location=to_location,
            reason=transfer.reason,
            message="Asset transferred successfully",
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{asset_id}/depreciation-history",
    response_model=DepreciationHistoryResponse,
    summary="Get depreciation history for an asset",
)
async def get_asset_depreciation_history(
    asset_id: UUID,
    limit: int = Query(100, ge=1, le=500, description="Maximum entries to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get the complete depreciation history for a specific asset.
    
    Returns chronological list of depreciation entries showing:
    - Period start/end dates
    - Depreciation amount for each period
    - Opening and closing net book values
    - Depreciation method used
    """
    service = FixedAssetService(db)
    
    asset = await service.get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    entries = await service.get_depreciation_history(asset_id, limit=limit)
    
    return DepreciationHistoryResponse(
        asset_id=asset.id,
        asset_name=asset.name,
        acquisition_cost=asset.acquisition_cost,
        accumulated_depreciation=asset.accumulated_depreciation,
        current_nbv=asset.net_book_value,
        entries=[
            DepreciationEntryResponse(
                id=entry.id,
                period_start=entry.period_start,
                period_end=entry.period_end,
                depreciation_amount=entry.depreciation_amount,
                opening_nbv=entry.opening_nbv,
                closing_nbv=entry.closing_nbv,
                method=entry.method,
                created_at=entry.created_at.isoformat() if entry.created_at else "",
            )
            for entry in entries
        ],
        total_entries=len(entries),
    )


@router.post(
    "/{asset_id}/restore",
    response_model=FixedAssetResponse,
    summary="Restore an archived asset",
)
async def restore_archived_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_organization_permission([OrganizationPermission.CREATE_TRANSACTIONS])
    ),
):
    """
    Restore a previously archived (soft-deleted) fixed asset.
    
    Returns the asset to ACTIVE status, making it available for
    depreciation and other operations.
    """
    service = FixedAssetService(db)
    
    asset = await service.get_asset_by_id(asset_id, include_archived=True)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if asset.status != AssetStatus.ARCHIVED:
        raise HTTPException(
            status_code=400,
            detail=f"Asset is not archived. Current status: {asset.status.value}"
        )
    
    try:
        restored_asset = await service.restore_asset(
            asset_id=asset_id,
            restored_by_id=current_user.id,
        )
        return _asset_to_response(restored_asset)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ===========================================
# HELPER FUNCTIONS
# ===========================================

def _asset_to_response(asset) -> FixedAssetResponse:
    """Convert asset model to response schema."""
    return FixedAssetResponse(
        id=asset.id,
        entity_id=asset.entity_id,
        name=asset.name,
        description=asset.description,
        asset_code=asset.asset_code,
        category=asset.category.value,
        status=asset.status.value,
        acquisition_date=asset.acquisition_date,
        acquisition_cost=asset.acquisition_cost,
        vendor_name=asset.vendor_name,
        vendor_irn=asset.vendor_irn,
        depreciation_method=asset.depreciation_method.value,
        useful_life_years=asset.useful_life_years,
        depreciation_rate=asset.depreciation_rate,
        residual_value=asset.residual_value,
        accumulated_depreciation=asset.accumulated_depreciation,
        net_book_value=asset.net_book_value,
        is_fully_depreciated=asset.is_fully_depreciated,
        location=asset.location,
        is_insured=asset.insured_value is not None and asset.insured_value > 0,
        insured_value=asset.insured_value,
        insurance_policy_number=asset.insurance_policy_number,
        created_at=asset.created_at.isoformat() if asset.created_at else "",
        updated_at=asset.updated_at.isoformat() if asset.updated_at else None,
    )
