"""
Tekvwa Pro Audit - Categories Router

API endpoints for category management with WREN classification.
"""

from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from datetime import datetime

from app.database import get_async_session
from app.dependencies import get_current_active_user
from app.models.user import User
from app.models.category import CategoryType, VATTreatment
from app.schemas.auth import MessageResponse
from app.services.category_service import CategoryService
from app.services.entity_service import EntityService
from app.services.audit_service import AuditService
from app.models.audit_consolidated import AuditAction


router = APIRouter()


# ===========================================
# SCHEMAS
# ===========================================

class CategoryCreateRequest(BaseModel):
    """Schema for creating a category."""
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=20)
    category_type: str = Field(..., description="Category type: income or expense")
    vat_treatment: str = Field("standard", description="VAT treatment: standard, zero_rated, exempt")
    description: Optional[str] = Field(None, max_length=500)
    parent_id: Optional[UUID] = None
    wren_default: bool = True
    wren_review_required: bool = False
    wren_notes: Optional[str] = None


class CategoryUpdateRequest(BaseModel):
    """Schema for updating a category."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    code: Optional[str] = Field(None, min_length=1, max_length=20)
    description: Optional[str] = Field(None, max_length=500)
    vat_treatment: Optional[str] = None
    parent_id: Optional[UUID] = None
    wren_default: Optional[bool] = None
    wren_review_required: Optional[bool] = None
    wren_notes: Optional[str] = None
    is_active: Optional[bool] = None


class CategoryResponse(BaseModel):
    """Schema for category response."""
    id: UUID
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    category_type: str
    vat_treatment: str
    parent_id: Optional[UUID] = None
    wren_default: bool
    wren_review_required: bool
    is_system: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class CategoryListResponse(BaseModel):
    """List of categories response."""
    categories: List[CategoryResponse]
    total: int


@router.get(
    "/{entity_id}/categories",
    response_model=CategoryListResponse,
    summary="List categories",
    description="Get all categories for a business entity.",
)
async def list_categories(
    entity_id: UUID,
    category_type: Optional[str] = Query(None, description="Filter by type: income, expense"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List all categories for an entity."""
    # Verify entity access
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    category_service = CategoryService(db)
    categories = await category_service.get_categories_for_entity(
        entity_id,
        category_type=category_type,
    )
    
    category_responses = [
        CategoryResponse(
            id=cat.id,
            name=cat.name,
            code=cat.code,
            description=cat.description,
            category_type=cat.category_type.value,
            vat_treatment=cat.vat_treatment.value,
            parent_id=cat.parent_id,
            wren_default=cat.wren_default,
            wren_review_required=cat.wren_review_required,
            is_system=cat.is_system,
            is_active=cat.is_active,
            created_at=cat.created_at,
            updated_at=cat.updated_at,
        )
        for cat in categories
    ]
    
    return CategoryListResponse(
        categories=category_responses,
        total=len(category_responses),
    )


@router.get(
    "/{entity_id}/categories/{category_id}",
    response_model=CategoryResponse,
    summary="Get category",
    description="Get a specific category by ID.",
)
async def get_category(
    entity_id: UUID,
    category_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific category."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    category_service = CategoryService(db)
    category = await category_service.get_category_by_id(category_id, entity_id)
    
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
        # Audit logging for category creation
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="category",
        entity_id=str(category.id),
        action=AuditAction.CREATE,
        user_id=current_user.id,
        new_values={
            "name": category.name,
            "code": category.code,
            "category_type": category.category_type.value,
            "vat_treatment": category.vat_treatment.value,
        }
    )
    
    return CategoryResponse(
        id=category.id,
        name=category.name,
        code=category.code,
        description=category.description,
        category_type=category.category_type.value,
        vat_treatment=category.vat_treatment.value,
        parent_id=category.parent_id,
        wren_default=category.wren_default,
        wren_review_required=category.wren_review_required,
        is_system=category.is_system,
        is_active=category.is_active,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


@router.post(
    "/{entity_id}/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create category",
    description="Create a new custom category for the entity.",
)
async def create_category(
    entity_id: UUID,
    request: CategoryCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a new category."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    can_write = await entity_service.check_user_can_write(current_user, entity_id)
    if not can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access denied for this entity",
        )
    
    # Parse enums
    try:
        cat_type = CategoryType(request.category_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category_type. Must be one of: {[t.value for t in CategoryType]}",
        )
    
    try:
        vat_treat = VATTreatment(request.vat_treatment)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid vat_treatment. Must be one of: {[t.value for t in VATTreatment]}",
        )
    
    category_service = CategoryService(db)
    
    try:
        category = await category_service.create_category(
            entity_id=entity_id,
            name=request.name,
            code=request.code,
            category_type=cat_type,
            vat_treatment=vat_treat,
            description=request.description,
            parent_id=request.parent_id,
            wren_default=request.wren_default,
            wren_review_required=request.wren_review_required,
            wren_notes=request.wren_notes,
            is_system=False,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return CategoryResponse(
        id=category.id,
        name=category.name,
        code=category.code,
        description=category.description,
        category_type=category.category_type.value,
        vat_treatment=category.vat_treatment.value,
        parent_id=category.parent_id,
        wren_default=category.wren_default,
        wren_review_required=category.wren_review_required,
        is_system=category.is_system,
        is_active=category.is_active,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


@router.patch(
    "/{entity_id}/categories/{category_id}",
    response_model=CategoryResponse,
    summary="Update category",
    description="Update a category. System categories have limited editable fields.",
)
async def update_category(
    entity_id: UUID,
    category_id: UUID,
    request: CategoryUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Update a category."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    can_write = await entity_service.check_user_can_write(current_user, entity_id)
    if not can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access denied for this entity",
        )
    
    category_service = CategoryService(db)
    category = await category_service.get_category_by_id(category_id, entity_id)
    
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
    
    update_data = request.model_dump(exclude_unset=True)
    
    # Parse vat_treatment if present
    if "vat_treatment" in update_data and update_data["vat_treatment"]:
        try:
            update_data["vat_treatment"] = VATTreatment(update_data["vat_treatment"])
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid vat_treatment. Must be one of: {[t.value for t in VATTreatment]}",
            )
    
    # Capture old values for audit
    old_values = {
        "name": category.name,
        "code": category.code,
        "description": category.description,
        "category_type": category.category_type.value if category.category_type else None,
        "vat_treatment": category.vat_treatment.value if category.vat_treatment else None,
        "is_active": category.is_active,
    }
    
    try:
        category = await category_service.update_category(category, **update_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # Audit logging for category update
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="category",
        entity_id=str(category.id),
        action=AuditAction.UPDATE,
        user_id=current_user.id,
        old_values=old_values,
        new_values={
            "name": category.name,
            "code": category.code,
            "description": category.description,
            "category_type": category.category_type.value if category.category_type else None,
            "vat_treatment": category.vat_treatment.value if category.vat_treatment else None,
            "is_active": category.is_active,
        }
    )
    
    return CategoryResponse(
        id=category.id,
        name=category.name,
        code=category.code,
        description=category.description,
        category_type=category.category_type.value,
        vat_treatment=category.vat_treatment.value,
        parent_id=category.parent_id,
        wren_default=category.wren_default,
        wren_review_required=category.wren_review_required,
        is_system=category.is_system,
        is_active=category.is_active,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


@router.delete(
    "/{entity_id}/categories/{category_id}",
    response_model=MessageResponse,
    summary="Delete category",
    description="Soft delete a category. System categories cannot be deleted.",
)
async def delete_category(
    entity_id: UUID,
    category_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete a category."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    can_write = await entity_service.check_user_can_write(current_user, entity_id)
    if not can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access denied for this entity",
        )
    
    category_service = CategoryService(db)
    category = await category_service.get_category_by_id(category_id, entity_id)
    
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
    
    # Capture values for audit before deletion
    deleted_category_data = {
        "name": category.name,
        "code": category.code,
        "category_type": category.category_type.value if category.category_type else None,
    }
    
    try:
        await category_service.delete_category(category)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # Audit logging for category deletion
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="category",
        entity_id=str(category_id),
        action=AuditAction.DELETE,
        user_id=current_user.id,
        old_values=deleted_category_data
    )
    
    return MessageResponse(
        message="Category deleted successfully",
        success=True,
    )


@router.post(
    "/{entity_id}/categories/initialize-defaults",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initialize default categories",
)
async def initialize_default_categories(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Initialize default WREN categories."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    can_write = await entity_service.check_user_can_write(current_user, entity_id)
    if not can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access denied for this entity",
        )
    
    category_service = CategoryService(db)
    
    existing = await category_service.get_categories_for_entity(entity_id)
    if any(cat.is_system for cat in existing):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Default categories already exist",
        )
    
    await category_service.create_default_categories(entity_id)
    
    return MessageResponse(
        message="Default WREN categories created successfully",
        success=True,
    )


# ===========================================
# CATEGORY TREE & HIERARCHY
# ===========================================

class CategoryTreeNode(BaseModel):
    """Category tree node with children."""
    id: UUID
    name: str
    code: Optional[str]
    category_type: str
    vat_treatment: str
    wren_default: bool
    is_system: bool
    is_active: bool
    transaction_count: int = 0
    children: List["CategoryTreeNode"] = []

    class Config:
        from_attributes = True


# Forward reference for recursive model
CategoryTreeNode.model_rebuild()


class CategoryTreeResponse(BaseModel):
    """Response for category tree."""
    entity_id: UUID
    income_categories: List[CategoryTreeNode]
    expense_categories: List[CategoryTreeNode]
    total_income_categories: int
    total_expense_categories: int


@router.get(
    "/{entity_id}/categories/tree",
    response_model=CategoryTreeResponse,
    summary="Get category tree",
    description="Get categories as a hierarchical tree structure.",
)
async def get_category_tree(
    entity_id: UUID,
    include_inactive: bool = Query(False, description="Include inactive categories"),
    include_transaction_count: bool = Query(False, description="Include transaction counts"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get categories organized as a hierarchical tree.
    
    Returns categories grouped by type (income/expense) with
    parent-child relationships represented as nested structures.
    """
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    category_service = CategoryService(db)
    categories = await category_service.get_categories_for_entity(
        entity_id,
        include_inactive=include_inactive,
    )
    
    # Build tree structure
    def build_tree(cats: list, parent_id: Optional[UUID] = None) -> List[CategoryTreeNode]:
        nodes = []
        for cat in cats:
            if cat.parent_id == parent_id:
                children = build_tree(cats, cat.id)
                nodes.append(CategoryTreeNode(
                    id=cat.id,
                    name=cat.name,
                    code=cat.code,
                    category_type=cat.category_type.value,
                    vat_treatment=cat.vat_treatment.value,
                    wren_default=cat.wren_default,
                    is_system=cat.is_system,
                    is_active=cat.is_active,
                    transaction_count=0,  # Would query if include_transaction_count
                    children=children,
                ))
        return nodes
    
    income_cats = [c for c in categories if c.category_type.value == "income"]
    expense_cats = [c for c in categories if c.category_type.value == "expense"]
    
    return CategoryTreeResponse(
        entity_id=entity_id,
        income_categories=build_tree(income_cats),
        expense_categories=build_tree(expense_cats),
        total_income_categories=len(income_cats),
        total_expense_categories=len(expense_cats),
    )


# ===========================================
# CATEGORY MERGE
# ===========================================

class MergeCategoriesRequest(BaseModel):
    """Request for merging categories."""
    source_category_ids: List[UUID] = Field(..., min_length=1, description="Categories to merge from")
    target_category_id: UUID = Field(..., description="Category to merge into")
    delete_source: bool = Field(True, description="Delete source categories after merge")


class MergeCategoriesResponse(BaseModel):
    """Response for category merge."""
    target_category_id: UUID
    transactions_moved: int
    source_categories_deleted: int
    message: str


@router.post(
    "/{entity_id}/categories/merge",
    response_model=MergeCategoriesResponse,
    summary="Merge categories",
    description="Merge multiple categories into a target category.",
)
async def merge_categories(
    entity_id: UUID,
    request: MergeCategoriesRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Merge multiple categories into one.
    
    This operation:
    - Moves all transactions from source categories to target
    - Optionally deletes the source categories
    - Cannot merge system categories
    - Cannot merge categories of different types (income/expense)
    
    Useful for consolidating similar categories or cleaning up
    duplicate categories created during import.
    """
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    can_write = await entity_service.check_user_can_write(current_user, entity_id)
    if not can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access denied for this entity",
        )
    
    # Validate target not in sources
    if request.target_category_id in request.source_category_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target category cannot be in source categories",
        )
    
    category_service = CategoryService(db)
    
    # Get target category
    target = await category_service.get_category_by_id(request.target_category_id, entity_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target category not found",
        )
    
    # Validate all source categories
    sources = []
    for source_id in request.source_category_ids:
        source = await category_service.get_category_by_id(source_id, entity_id)
        if not source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Source category {source_id} not found",
            )
        if source.is_system:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot merge system category: {source.name}",
            )
        if source.category_type != target.category_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot merge {source.category_type.value} category into {target.category_type.value} category",
            )
        sources.append(source)
    
    try:
        transactions_moved = await category_service.merge_categories(
            source_categories=sources,
            target_category=target,
            delete_source=request.delete_source,
        )
        
        await db.commit()
        
        return MergeCategoriesResponse(
            target_category_id=target.id,
            transactions_moved=transactions_moved,
            source_categories_deleted=len(sources) if request.delete_source else 0,
            message=f"Successfully merged {len(sources)} categories. {transactions_moved} transactions moved.",
        )
        
    except ValueError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ===========================================
# CATEGORY RESTORE
# ===========================================

@router.post(
    "/{entity_id}/categories/{category_id}/restore",
    response_model=CategoryResponse,
    summary="Restore deleted category",
    description="Restore a previously deleted (soft-deleted) category.",
)
async def restore_category(
    entity_id: UUID,
    category_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Restore a deleted category.
    
    This reactivates a soft-deleted category, making it available
    for use in transactions again.
    """
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    can_write = await entity_service.check_user_can_write(current_user, entity_id)
    if not can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access denied for this entity",
        )
    
    category_service = CategoryService(db)
    
    # Get category including inactive
    category = await category_service.get_category_by_id(
        category_id, 
        entity_id, 
        include_inactive=True
    )
    
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
    
    if category.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category is not deleted",
        )
    
    try:
        category = await category_service.restore_category(category)
        await db.commit()
        
        return CategoryResponse(
            id=category.id,
            name=category.name,
            code=category.code,
            description=category.description,
            category_type=category.category_type.value,
            vat_treatment=category.vat_treatment.value,
            parent_id=category.parent_id,
            wren_default=category.wren_default,
            wren_review_required=category.wren_review_required,
            is_system=category.is_system,
            is_active=category.is_active,
            created_at=category.created_at,
            updated_at=category.updated_at,
        )
        
    except ValueError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/{entity_id}/categories/deleted",
    response_model=CategoryListResponse,
    summary="List deleted categories",
    description="Get all deleted (inactive) categories that can be restored.",
)
async def list_deleted_categories(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List all deleted categories for possible restoration."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    category_service = CategoryService(db)
    categories = await category_service.get_deleted_categories(entity_id)
    
    category_responses = [
        CategoryResponse(
            id=cat.id,
            name=cat.name,
            code=cat.code,
            description=cat.description,
            category_type=cat.category_type.value,
            vat_treatment=cat.vat_treatment.value,
            parent_id=cat.parent_id,
            wren_default=cat.wren_default,
            wren_review_required=cat.wren_review_required,
            is_system=cat.is_system,
            is_active=cat.is_active,
            created_at=cat.created_at,
            updated_at=cat.updated_at,
        )
        for cat in categories
    ]
    
    return CategoryListResponse(
        categories=category_responses,
        total=len(category_responses),
    )


# ===========================================
# CATEGORY STATISTICS
# ===========================================

class CategoryStatsResponse(BaseModel):
    """Statistics for a category."""
    category_id: UUID
    category_name: str
    transaction_count: int
    total_amount: float
    average_amount: float
    last_used: Optional[datetime]
    usage_trend: str  # increasing, decreasing, stable


@router.get(
    "/{entity_id}/categories/{category_id}/stats",
    response_model=CategoryStatsResponse,
    summary="Get category statistics",
    description="Get usage statistics for a category.",
)
async def get_category_stats(
    entity_id: UUID,
    category_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get usage statistics for a category."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    category_service = CategoryService(db)
    category = await category_service.get_category_by_id(category_id, entity_id)
    
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
    
    stats = await category_service.get_category_stats(category_id)
    
    return CategoryStatsResponse(
        category_id=category.id,
        category_name=category.name,
        transaction_count=stats.get("transaction_count", 0),
        total_amount=stats.get("total_amount", 0),
        average_amount=stats.get("average_amount", 0),
        last_used=stats.get("last_used"),
        usage_trend=stats.get("usage_trend", "stable"),
    )
