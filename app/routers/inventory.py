"""
Tekvwa Pro Audit - Inventory Router

API endpoints for inventory management, stock tracking, and write-offs.
"""

from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import get_current_active_user, require_within_usage_limit, record_usage_event, require_feature
from app.models.user import User
from app.models.audit_consolidated import AuditAction
from app.models.sku import UsageMetricType, Feature
from app.services.entity_service import EntityService
from app.services.inventory_service import InventoryService
from app.services.audit_service import AuditService
from app.schemas.inventory import (
    InventoryItemCreate,
    InventoryItemUpdate,
    InventoryItemResponse,
    InventoryItemListResponse,
    StockMovementCreate,
    StockMovementResponse,
    StockReceiveRequest,
    StockSaleRequest,
    StockAdjustmentRequest,
    StockWriteOffCreate,
    StockWriteOffResponse,
    StockWriteOffReviewRequest,
    InventorySummaryResponse,
    LowStockAlertResponse,
)
from app.schemas.auth import MessageResponse

# Feature gate for inventory (CORE tier - basic inventory access)
inventory_feature_gate = require_feature([Feature.INVENTORY_BASIC])

router = APIRouter(dependencies=[Depends(inventory_feature_gate)])


# ===========================================
# HELPER FUNCTIONS
# ===========================================

async def verify_entity_access(
    entity_id: UUID,
    user: User,
    db: AsyncSession,
) -> None:
    """Verify user has access to the entity."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, user)
    
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business entity not found",
        )
    
    has_access = any(
        access.entity_id == entity_id 
        for access in user.entity_access
    )
    
    if not has_access and entity.organization_id != user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this business entity",
        )


# ===========================================
# INVENTORY ITEM ENDPOINTS
# ===========================================

@router.get(
    "/{entity_id}/inventory",
    response_model=InventoryItemListResponse,
    summary="List inventory items",
)
async def list_inventory_items(
    entity_id: UUID,
    category: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    low_stock_only: bool = Query(False),
    search: Optional[str] = Query(None, description="Search by SKU, name, or barcode"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    List inventory items for a business entity.
    
    Supports filtering by:
    - category
    - active status
    - low stock items only
    - search (SKU, name, barcode)
    """
    await verify_entity_access(entity_id, current_user, db)
    
    service = InventoryService(db)
    items, total, low_stock_count = await service.get_items_for_entity(
        entity_id=entity_id,
        category=category,
        is_active=is_active,
        low_stock_only=low_stock_only,
        search=search,
        skip=skip,
        limit=limit,
    )
    
    return InventoryItemListResponse(
        items=[
            InventoryItemResponse(
                id=item.id,
                entity_id=item.entity_id,
                sku=item.sku,
                name=item.name,
                description=item.description,
                barcode=item.barcode,
                category=item.category,
                unit_cost=float(item.unit_cost),
                unit_price=float(item.unit_price),
                quantity_on_hand=item.quantity_on_hand,
                reorder_level=item.reorder_level,
                reorder_quantity=item.reorder_quantity,
                unit_of_measure=item.unit_of_measure,
                is_active=item.is_active,
                is_tracked=item.is_tracked,
                is_low_stock=item.is_low_stock,
                stock_value=float(item.stock_value),
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in items
        ],
        total=total,
        low_stock_count=low_stock_count,
    )


@router.post(
    "/{entity_id}/inventory",
    response_model=InventoryItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create inventory item",
)
async def create_inventory_item(
    entity_id: UUID,
    request: InventoryItemCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
    _limit_check: User = Depends(require_within_usage_limit(UsageMetricType.TRANSACTIONS)),
):
    """Create a new inventory item."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = InventoryService(db)
    
    try:
        item = await service.create_item(
            entity_id=entity_id,
            sku=request.sku,
            name=request.name,
            description=request.description,
            barcode=request.barcode,
            category=request.category,
            unit_cost=request.unit_cost,
            unit_price=request.unit_price,
            quantity_on_hand=request.quantity_on_hand,
            reorder_level=request.reorder_level,
            reorder_quantity=request.reorder_quantity,
            unit_of_measure=request.unit_of_measure,
            is_tracked=request.is_tracked,
            created_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # Record usage metering for inventory item creation
    if current_user.organization_id:
        await record_usage_event(
            db=db,
            organization_id=current_user.organization_id,
            metric_type=UsageMetricType.TRANSACTIONS,
            entity_id=entity_id,
            user_id=current_user.id,
            resource_type="inventory_item",
            resource_id=str(item.id),
        )
    
    return InventoryItemResponse(
        id=item.id,
        entity_id=item.entity_id,
        sku=item.sku,
        name=item.name,
        description=item.description,
        barcode=item.barcode,
        category=item.category,
        unit_cost=float(item.unit_cost),
        unit_price=float(item.unit_price),
        quantity_on_hand=item.quantity_on_hand,
        reorder_level=item.reorder_level,
        reorder_quantity=item.reorder_quantity,
        unit_of_measure=item.unit_of_measure,
        is_active=item.is_active,
        is_tracked=item.is_tracked,
        is_low_stock=item.is_low_stock,
        stock_value=float(item.stock_value),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get(
    "/{entity_id}/inventory/{item_id}",
    response_model=InventoryItemResponse,
    summary="Get inventory item",
)
async def get_inventory_item(
    entity_id: UUID,
    item_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific inventory item."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = InventoryService(db)
    item = await service.get_item_by_id(item_id)
    
    if not item or item.entity_id != entity_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )
    
    return InventoryItemResponse(
        id=item.id,
        entity_id=item.entity_id,
        sku=item.sku,
        name=item.name,
        description=item.description,
        barcode=item.barcode,
        category=item.category,
        unit_cost=float(item.unit_cost),
        unit_price=float(item.unit_price),
        quantity_on_hand=item.quantity_on_hand,
        reorder_level=item.reorder_level,
        reorder_quantity=item.reorder_quantity,
        unit_of_measure=item.unit_of_measure,
        is_active=item.is_active,
        is_tracked=item.is_tracked,
        is_low_stock=item.is_low_stock,
        stock_value=float(item.stock_value),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.patch(
    "/{entity_id}/inventory/{item_id}",
    response_model=InventoryItemResponse,
    summary="Update inventory item",
)
async def update_inventory_item(
    entity_id: UUID,
    item_id: UUID,
    request: InventoryItemUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Update an inventory item."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = InventoryService(db)
    
    # Verify item belongs to entity
    existing = await service.get_item_by_id(item_id)
    if not existing or existing.entity_id != entity_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )
    
    # Store old values for audit
    old_values = {
        "sku": existing.sku,
        "name": existing.name,
        "unit_cost": float(existing.unit_cost),
        "unit_price": float(existing.unit_price),
        "quantity_on_hand": existing.quantity_on_hand,
    }
    
    update_data = request.model_dump(exclude_unset=True)
    
    try:
        item = await service.update_item(item_id, update_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # Audit log for inventory item update
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="inventory_item",
        entity_id=str(item.id),
        action=AuditAction.UPDATE,
        user_id=current_user.id,
        old_values=old_values,
        new_values=update_data,
    )
    
    return InventoryItemResponse(
        id=item.id,
        entity_id=item.entity_id,
        sku=item.sku,
        name=item.name,
        description=item.description,
        barcode=item.barcode,
        category=item.category,
        unit_cost=float(item.unit_cost),
        unit_price=float(item.unit_price),
        quantity_on_hand=item.quantity_on_hand,
        reorder_level=item.reorder_level,
        reorder_quantity=item.reorder_quantity,
        unit_of_measure=item.unit_of_measure,
        is_active=item.is_active,
        is_tracked=item.is_tracked,
        is_low_stock=item.is_low_stock,
        stock_value=float(item.stock_value),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.delete(
    "/{entity_id}/inventory/{item_id}",
    response_model=MessageResponse,
    summary="Delete inventory item",
)
async def delete_inventory_item(
    entity_id: UUID,
    item_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete (deactivate) an inventory item."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = InventoryService(db)
    
    existing = await service.get_item_by_id(item_id)
    if not existing or existing.entity_id != entity_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )
    
    # Store inventory item data for audit before deletion
    deleted_values = {
        "sku": existing.sku,
        "name": existing.name,
        "quantity_on_hand": existing.quantity_on_hand,
    }
    deleted_id = str(existing.id)
    
    await service.delete_item(item_id)
    
    # Audit log for inventory item deletion
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="inventory_item",
        entity_id=deleted_id,
        action=AuditAction.DELETE,
        user_id=current_user.id,
        old_values=deleted_values,
    )
    
    return MessageResponse(message="Inventory item deactivated successfully")


# ===========================================
# STOCK OPERATIONS
# ===========================================

@router.post(
    "/{entity_id}/inventory/{item_id}/receive",
    response_model=InventoryItemResponse,
    summary="Receive stock",
)
async def receive_stock(
    entity_id: UUID,
    item_id: UUID,
    request: StockReceiveRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Receive stock from a purchase.
    
    Updates stock quantity and weighted average cost.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    service = InventoryService(db)
    
    existing = await service.get_item_by_id(item_id)
    if not existing or existing.entity_id != entity_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )
    
    try:
        item = await service.receive_stock(
            item_id=item_id,
            quantity=request.quantity,
            unit_cost=request.unit_cost,
            reference=request.reference,
            notes=request.notes,
            receive_date=request.receive_date,
            created_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return InventoryItemResponse(
        id=item.id,
        entity_id=item.entity_id,
        sku=item.sku,
        name=item.name,
        description=item.description,
        barcode=item.barcode,
        category=item.category,
        unit_cost=float(item.unit_cost),
        unit_price=float(item.unit_price),
        quantity_on_hand=item.quantity_on_hand,
        reorder_level=item.reorder_level,
        reorder_quantity=item.reorder_quantity,
        unit_of_measure=item.unit_of_measure,
        is_active=item.is_active,
        is_tracked=item.is_tracked,
        is_low_stock=item.is_low_stock,
        stock_value=float(item.stock_value),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post(
    "/{entity_id}/inventory/{item_id}/sale",
    response_model=InventoryItemResponse,
    summary="Record sale",
)
async def record_sale(
    entity_id: UUID,
    item_id: UUID,
    request: StockSaleRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Record a sale (reduce stock).
    """
    await verify_entity_access(entity_id, current_user, db)
    
    service = InventoryService(db)
    
    existing = await service.get_item_by_id(item_id)
    if not existing or existing.entity_id != entity_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )
    
    try:
        item = await service.record_sale(
            item_id=item_id,
            quantity=request.quantity,
            reference=request.reference,
            notes=request.notes,
            sale_date=request.sale_date,
            created_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return InventoryItemResponse(
        id=item.id,
        entity_id=item.entity_id,
        sku=item.sku,
        name=item.name,
        description=item.description,
        barcode=item.barcode,
        category=item.category,
        unit_cost=float(item.unit_cost),
        unit_price=float(item.unit_price),
        quantity_on_hand=item.quantity_on_hand,
        reorder_level=item.reorder_level,
        reorder_quantity=item.reorder_quantity,
        unit_of_measure=item.unit_of_measure,
        is_active=item.is_active,
        is_tracked=item.is_tracked,
        is_low_stock=item.is_low_stock,
        stock_value=float(item.stock_value),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post(
    "/{entity_id}/inventory/{item_id}/adjust",
    response_model=InventoryItemResponse,
    summary="Adjust stock",
)
async def adjust_stock(
    entity_id: UUID,
    item_id: UUID,
    request: StockAdjustmentRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Adjust stock quantity (positive or negative).
    
    Use this for physical count corrections, etc.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    service = InventoryService(db)
    
    existing = await service.get_item_by_id(item_id)
    if not existing or existing.entity_id != entity_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )
    
    try:
        item = await service.adjust_stock(
            item_id=item_id,
            quantity_change=request.quantity_change,
            reason=request.reason,
            reference=request.reference,
            adjustment_date=request.adjustment_date,
            created_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return InventoryItemResponse(
        id=item.id,
        entity_id=item.entity_id,
        sku=item.sku,
        name=item.name,
        description=item.description,
        barcode=item.barcode,
        category=item.category,
        unit_cost=float(item.unit_cost),
        unit_price=float(item.unit_price),
        quantity_on_hand=item.quantity_on_hand,
        reorder_level=item.reorder_level,
        reorder_quantity=item.reorder_quantity,
        unit_of_measure=item.unit_of_measure,
        is_active=item.is_active,
        is_tracked=item.is_tracked,
        is_low_stock=item.is_low_stock,
        stock_value=float(item.stock_value),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get(
    "/{entity_id}/inventory/{item_id}/movements",
    response_model=List[StockMovementResponse],
    summary="Get stock movements",
)
async def get_stock_movements(
    entity_id: UUID,
    item_id: UUID,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    movement_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get stock movement history for an item."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = InventoryService(db)
    
    existing = await service.get_item_by_id(item_id)
    if not existing or existing.entity_id != entity_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )
    
    from app.models.inventory import StockMovementType
    
    mt = None
    if movement_type:
        try:
            mt = StockMovementType(movement_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid movement type. Valid types: {[t.value for t in StockMovementType]}",
            )
    
    movements = await service.get_movements_for_item(
        item_id=item_id,
        start_date=start_date,
        end_date=end_date,
        movement_type=mt,
        limit=limit,
    )
    
    return [
        StockMovementResponse(
            id=m.id,
            item_id=m.item_id,
            movement_type=m.movement_type.value,
            quantity=m.quantity,
            unit_cost=float(m.unit_cost),
            reference=m.reference,
            notes=m.notes,
            movement_date=m.movement_date,
            created_at=m.created_at,
            created_by=m.created_by,
        )
        for m in movements
    ]


# ===========================================
# WRITE-OFF ENDPOINTS
# ===========================================

@router.post(
    "/{entity_id}/inventory/{item_id}/write-off",
    response_model=StockWriteOffResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create write-off",
)
async def create_write_off(
    entity_id: UUID,
    item_id: UUID,
    request: StockWriteOffCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create a stock write-off for damaged/expired goods.
    
    Write-offs are flagged for tax deduction review.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    service = InventoryService(db)
    
    existing = await service.get_item_by_id(item_id)
    if not existing or existing.entity_id != entity_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )
    
    try:
        write_off = await service.create_write_off(
            item_id=item_id,
            quantity=request.quantity,
            reason=request.reason,
            notes=request.notes,
            documentation_url=request.documentation_url,
            write_off_date=request.write_off_date,
            is_tax_deductible=request.is_tax_deductible,
            created_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return StockWriteOffResponse(
        id=write_off.id,
        item_id=write_off.item_id,
        quantity=write_off.quantity,
        unit_cost=float(write_off.unit_cost),
        total_value=float(write_off.total_value),
        reason=write_off.reason.value,
        notes=write_off.notes,
        documentation_url=write_off.documentation_url,
        write_off_date=write_off.write_off_date,
        is_tax_deductible=write_off.is_tax_deductible,
        reviewed=write_off.reviewed,
        reviewed_at=write_off.reviewed_at,
        created_at=write_off.created_at,
        created_by=write_off.created_by,
    )


@router.get(
    "/{entity_id}/write-offs",
    response_model=List[StockWriteOffResponse],
    summary="List write-offs",
)
async def list_write_offs(
    entity_id: UUID,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    reviewed: Optional[bool] = Query(None),
    is_tax_deductible: Optional[bool] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List all write-offs for a business entity."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = InventoryService(db)
    write_offs = await service.get_write_offs_for_entity(
        entity_id=entity_id,
        start_date=start_date,
        end_date=end_date,
        reviewed=reviewed,
        is_tax_deductible=is_tax_deductible,
    )
    
    return [
        StockWriteOffResponse(
            id=wo.id,
            item_id=wo.item_id,
            quantity=wo.quantity,
            unit_cost=float(wo.unit_cost),
            total_value=float(wo.total_value),
            reason=wo.reason.value,
            notes=wo.notes,
            documentation_url=wo.documentation_url,
            write_off_date=wo.write_off_date,
            is_tax_deductible=wo.is_tax_deductible,
            reviewed=wo.reviewed,
            reviewed_at=wo.reviewed_at,
            created_at=wo.created_at,
            created_by=wo.created_by,
        )
        for wo in write_offs
    ]


@router.post(
    "/{entity_id}/write-offs/{write_off_id}/review",
    response_model=StockWriteOffResponse,
    summary="Review write-off",
)
async def review_write_off(
    entity_id: UUID,
    write_off_id: UUID,
    request: StockWriteOffReviewRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Review a write-off (accountant/auditor approval).
    
    Confirms tax deductibility status.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    service = InventoryService(db)
    
    try:
        write_off = await service.review_write_off(
            write_off_id=write_off_id,
            is_tax_deductible=request.is_tax_deductible,
            notes=request.notes,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    
    return StockWriteOffResponse(
        id=write_off.id,
        item_id=write_off.item_id,
        quantity=write_off.quantity,
        unit_cost=float(write_off.unit_cost),
        total_value=float(write_off.total_value),
        reason=write_off.reason.value,
        notes=write_off.notes,
        documentation_url=write_off.documentation_url,
        write_off_date=write_off.write_off_date,
        is_tax_deductible=write_off.is_tax_deductible,
        reviewed=write_off.reviewed,
        reviewed_at=write_off.reviewed_at,
        created_at=write_off.created_at,
        created_by=write_off.created_by,
    )


# ===========================================
# REPORTS & ALERTS
# ===========================================

@router.get(
    "/{entity_id}/inventory/summary",
    response_model=InventorySummaryResponse,
    summary="Get inventory summary",
)
async def get_inventory_summary(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get inventory summary for a business entity."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = InventoryService(db)
    summary = await service.get_inventory_summary(entity_id)
    
    return InventorySummaryResponse(**summary)


@router.get(
    "/{entity_id}/inventory/low-stock",
    response_model=List[LowStockAlertResponse],
    summary="Get low stock alerts",
)
async def get_low_stock_alerts(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get items with stock at or below reorder level."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = InventoryService(db)
    alerts = await service.get_low_stock_alerts(entity_id)
    
    return [LowStockAlertResponse(**a) for a in alerts]


# ===========================================
# STOCKTAKE & VALUATION
# ===========================================

from pydantic import BaseModel, Field
from decimal import Decimal


class StocktakeItemEntry(BaseModel):
    """Entry for a single item in a stocktake."""
    item_id: UUID
    physical_count: int = Field(..., ge=0, description="Physical count from stocktake")
    notes: Optional[str] = None


class StocktakeRequest(BaseModel):
    """Request schema for recording a stocktake."""
    stocktake_date: date
    reference: Optional[str] = Field(None, max_length=100, description="Stocktake reference number")
    items: List[StocktakeItemEntry] = Field(..., min_length=1)
    notes: Optional[str] = None


class StocktakeItemResult(BaseModel):
    """Result for a single item after stocktake processing."""
    item_id: UUID
    sku: str
    name: str
    system_quantity: int
    physical_count: int
    variance: int
    variance_value: float
    adjustment_applied: bool


class StocktakeResponse(BaseModel):
    """Response schema for stocktake completion."""
    stocktake_id: UUID
    stocktake_date: date
    reference: Optional[str]
    total_items: int
    items_with_variance: int
    total_variance_value: float
    results: List[StocktakeItemResult]
    message: str


class InventoryValuationItem(BaseModel):
    """Valuation details for a single inventory item."""
    item_id: UUID
    sku: str
    name: str
    category: Optional[str]
    quantity_on_hand: int
    unit_cost: float
    total_value: float
    last_received_date: Optional[date]
    last_movement_date: Optional[date]


class InventoryValuationResponse(BaseModel):
    """Response schema for inventory valuation report."""
    entity_id: UUID
    valuation_date: date
    valuation_method: str
    total_items: int
    total_quantity: int
    total_value: float
    items_by_category: dict
    items: List[InventoryValuationItem]


class InventoryCategoryResponse(BaseModel):
    """Response schema for inventory category."""
    name: str
    item_count: int
    total_quantity: int
    total_value: float
    low_stock_count: int


@router.post(
    "/{entity_id}/inventory/stocktake",
    response_model=StocktakeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record stocktake results",
)
async def record_stocktake(
    entity_id: UUID,
    request: StocktakeRequest,
    apply_adjustments: bool = Query(True, description="Automatically apply stock adjustments"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Record physical stocktake results and optionally apply adjustments.
    
    This endpoint:
    - Compares physical counts against system quantities
    - Calculates variances and their values
    - Optionally applies stock adjustments to reconcile differences
    - Creates an audit trail for all adjustments
    
    For 2026 compliance, all stock adjustments are tracked for
    inventory write-off and tax deduction purposes.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    service = InventoryService(db)
    
    results = []
    items_with_variance = 0
    total_variance_value = 0.0
    
    # Generate stocktake ID
    import uuid
    stocktake_id = uuid.uuid4()
    
    for entry in request.items:
        item = await service.get_item_by_id(entry.item_id)
        if not item or item.entity_id != entity_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Inventory item {entry.item_id} not found",
            )
        
        system_qty = item.quantity_on_hand
        variance = entry.physical_count - system_qty
        variance_value = float(variance * item.unit_cost)
        
        adjustment_applied = False
        
        if variance != 0:
            items_with_variance += 1
            total_variance_value += variance_value
            
            if apply_adjustments:
                try:
                    await service.adjust_stock(
                        item_id=entry.item_id,
                        quantity_change=variance,
                        reason=f"Stocktake adjustment - Ref: {request.reference or stocktake_id}",
                        reference=request.reference or f"STOCKTAKE-{stocktake_id}",
                        adjustment_date=request.stocktake_date,
                        created_by=current_user.id,
                    )
                    adjustment_applied = True
                except ValueError:
                    adjustment_applied = False
        
        results.append(StocktakeItemResult(
            item_id=item.id,
            sku=item.sku,
            name=item.name,
            system_quantity=system_qty,
            physical_count=entry.physical_count,
            variance=variance,
            variance_value=variance_value,
            adjustment_applied=adjustment_applied,
        ))
    
    return StocktakeResponse(
        stocktake_id=stocktake_id,
        stocktake_date=request.stocktake_date,
        reference=request.reference,
        total_items=len(request.items),
        items_with_variance=items_with_variance,
        total_variance_value=total_variance_value,
        results=results,
        message=f"Stocktake recorded. {items_with_variance} items had variances." + 
                (f" Adjustments applied." if apply_adjustments else " Review and apply adjustments manually."),
    )


@router.get(
    "/{entity_id}/inventory/valuation",
    response_model=InventoryValuationResponse,
    summary="Get inventory valuation report",
)
async def get_inventory_valuation(
    entity_id: UUID,
    valuation_date: Optional[date] = Query(None, description="Valuation as of date (defaults to today)"),
    category: Optional[str] = Query(None, description="Filter by category"),
    include_zero_stock: bool = Query(False, description="Include items with zero stock"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get comprehensive inventory valuation report.
    
    Returns inventory valuation using weighted average cost method,
    which is the standard for Nigeria tax compliance.
    
    The report includes:
    - Individual item valuations
    - Category totals
    - Overall inventory value
    - Last movement dates for aging analysis
    """
    from datetime import date as date_type
    
    await verify_entity_access(entity_id, current_user, db)
    
    service = InventoryService(db)
    
    effective_date = valuation_date or date_type.today()
    
    # Get all items
    items, total, _ = await service.get_items_for_entity(
        entity_id=entity_id,
        category=category,
        is_active=True,
        skip=0,
        limit=10000,  # Get all for valuation
    )
    
    valuation_items = []
    items_by_category = {}
    total_quantity = 0
    total_value = 0.0
    
    for item in items:
        if not include_zero_stock and item.quantity_on_hand <= 0:
            continue
        
        item_value = float(item.quantity_on_hand * item.unit_cost)
        total_quantity += item.quantity_on_hand
        total_value += item_value
        
        # Track by category
        cat_name = item.category or "Uncategorized"
        if cat_name not in items_by_category:
            items_by_category[cat_name] = {
                "item_count": 0,
                "quantity": 0,
                "value": 0.0,
            }
        items_by_category[cat_name]["item_count"] += 1
        items_by_category[cat_name]["quantity"] += item.quantity_on_hand
        items_by_category[cat_name]["value"] += item_value
        
        valuation_items.append(InventoryValuationItem(
            item_id=item.id,
            sku=item.sku,
            name=item.name,
            category=item.category,
            quantity_on_hand=item.quantity_on_hand,
            unit_cost=float(item.unit_cost),
            total_value=item_value,
            last_received_date=None,  # Would need to query movements
            last_movement_date=None,
        ))
    
    return InventoryValuationResponse(
        entity_id=entity_id,
        valuation_date=effective_date,
        valuation_method="Weighted Average Cost",
        total_items=len(valuation_items),
        total_quantity=total_quantity,
        total_value=total_value,
        items_by_category=items_by_category,
        items=valuation_items,
    )


@router.get(
    "/{entity_id}/inventory/categories",
    response_model=List[InventoryCategoryResponse],
    summary="List inventory categories",
)
async def list_inventory_categories(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    List all inventory categories for the entity with statistics.
    
    Returns:
    - Category name
    - Number of items in category
    - Total quantity across all items
    - Total value of category
    - Count of low stock items
    """
    await verify_entity_access(entity_id, current_user, db)
    
    service = InventoryService(db)
    
    # Get all items
    items, _, _ = await service.get_items_for_entity(
        entity_id=entity_id,
        is_active=True,
        skip=0,
        limit=10000,
    )
    
    categories = {}
    
    for item in items:
        cat_name = item.category or "Uncategorized"
        
        if cat_name not in categories:
            categories[cat_name] = {
                "name": cat_name,
                "item_count": 0,
                "total_quantity": 0,
                "total_value": 0.0,
                "low_stock_count": 0,
            }
        
        categories[cat_name]["item_count"] += 1
        categories[cat_name]["total_quantity"] += item.quantity_on_hand
        categories[cat_name]["total_value"] += float(item.quantity_on_hand * item.unit_cost)
        
        if item.is_low_stock:
            categories[cat_name]["low_stock_count"] += 1
    
    return [
        InventoryCategoryResponse(
            name=cat["name"],
            item_count=cat["item_count"],
            total_quantity=cat["total_quantity"],
            total_value=cat["total_value"],
            low_stock_count=cat["low_stock_count"],
        )
        for cat in sorted(categories.values(), key=lambda x: x["name"])
    ]
