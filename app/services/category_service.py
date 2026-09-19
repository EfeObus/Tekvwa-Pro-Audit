"""
Tekvwa Pro Audit - Category Service

Business logic for category management with WREN classification.
"""

import uuid
from typing import List, Optional, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category, VATTreatment, CategoryType


# Default categories following Nigerian tax structure
DEFAULT_CATEGORIES: List[Dict[str, Any]] = [
    # INCOME CATEGORIES
    {
        "name": "Sales Revenue",
        "code": "4000",
        "category_type": CategoryType.INCOME,
        "vat_treatment": VATTreatment.STANDARD,
        "description": "Revenue from sale of goods and services",
    },
    {
        "name": "Service Income",
        "code": "4100",
        "category_type": CategoryType.INCOME,
        "vat_treatment": VATTreatment.STANDARD,
        "description": "Income from services rendered",
    },
    {
        "name": "Export Sales",
        "code": "4400",
        "category_type": CategoryType.INCOME,
        "vat_treatment": VATTreatment.ZERO_RATED,
        "description": "Zero-rated export revenue",
    },
    
    # EXPENSE CATEGORIES
    {
        "name": "Cost of Goods Sold",
        "code": "5000",
        "category_type": CategoryType.EXPENSE,
        "vat_treatment": VATTreatment.STANDARD,
        "description": "Direct cost of inventory sold",
        "wren_default": True,
    },
    {
        "name": "Salaries and Wages",
        "code": "6000",
        "category_type": CategoryType.EXPENSE,
        "vat_treatment": VATTreatment.EXEMPT,
        "description": "Employee compensation",
        "wren_default": True,
    },
    {
        "name": "Office Supplies",
        "code": "6300",
        "category_type": CategoryType.EXPENSE,
        "vat_treatment": VATTreatment.STANDARD,
        "description": "General office supplies and materials",
        "wren_default": True,
    },
    {
        "name": "Utilities",
        "code": "6400",
        "category_type": CategoryType.EXPENSE,
        "vat_treatment": VATTreatment.EXEMPT,
        "description": "Electricity, water, internet",
        "wren_default": True,
    },
    {
        "name": "Transportation",
        "code": "6500",
        "category_type": CategoryType.EXPENSE,
        "vat_treatment": VATTreatment.STANDARD,
        "description": "Vehicle, logistics, delivery costs",
        "wren_default": True,
    },
]


class CategoryService:
    """Service for category operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_categories_for_entity(
        self,
        entity_id: uuid.UUID,
        category_type: Optional[str] = None,
        include_inactive: bool = False,
    ) -> List[Category]:
        """Get all categories (shared across entities for now)."""
        query = select(Category)
        
        if category_type:
            cat_type = CategoryType(category_type)
            query = query.where(Category.category_type == cat_type)
        
        if not include_inactive:
            query = query.where(Category.is_active == True)
        
        query = query.order_by(Category.code)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_category_by_id(
        self,
        category_id: uuid.UUID,
        entity_id: uuid.UUID = None,
    ) -> Optional[Category]:
        """Get category by ID."""
        result = await self.db.execute(
            select(Category).where(Category.id == category_id)
        )
        return result.scalar_one_or_none()
    
    async def get_category_by_code(
        self,
        code: str,
        entity_id: uuid.UUID = None,
    ) -> Optional[Category]:
        """Get category by code."""
        result = await self.db.execute(
            select(Category).where(Category.code == code)
        )
        return result.scalar_one_or_none()
    
    async def create_category(
        self,
        entity_id: uuid.UUID,
        name: str,
        code: str,
        category_type: CategoryType,
        vat_treatment: VATTreatment = VATTreatment.STANDARD,
        description: Optional[str] = None,
        parent_id: Optional[uuid.UUID] = None,
        wren_default: bool = True,
        wren_review_required: bool = False,
        wren_notes: Optional[str] = None,
        is_system: bool = False,
        **kwargs,
    ) -> Category:
        """Create a new category."""
        existing = await self.get_category_by_code(code)
        if existing:
            raise ValueError(f"Category with code '{code}' already exists")
        
        category = Category(
            name=name,
            code=code,
            category_type=category_type,
            vat_treatment=vat_treatment,
            description=description,
            parent_id=parent_id,
            wren_default=wren_default,
            wren_review_required=wren_review_required,
            wren_notes=wren_notes,
            is_system=is_system,
            is_active=True,
        )
        
        self.db.add(category)
        await self.db.commit()
        await self.db.refresh(category)
        
        return category
    
    async def update_category(
        self,
        category: Category,
        **kwargs,
    ) -> Category:
        """Update a category."""
        if category.is_system:
            allowed = {"description", "vat_treatment", "wren_notes"}
            for key in kwargs:
                if key not in allowed and kwargs[key] is not None:
                    raise ValueError(f"Cannot modify '{key}' on system category")
        
        for key, value in kwargs.items():
            if value is not None and hasattr(category, key):
                setattr(category, key, value)
        
        await self.db.commit()
        await self.db.refresh(category)
        
        return category
    
    async def delete_category(self, category: Category) -> bool:
        """Soft delete a category."""
        if category.is_system:
            raise ValueError("Cannot delete system category")
        
        category.is_active = False
        await self.db.commit()
        return True
    
    async def create_default_categories(self, entity_id: uuid.UUID = None) -> List[Category]:
        """Create default categories."""
        created = []
        
        for cat_data in DEFAULT_CATEGORIES:
            try:
                category = await self.create_category(
                    entity_id=entity_id,
                    is_system=True,
                    **cat_data,
                )
                created.append(category)
            except ValueError:
                pass
        
        return created
