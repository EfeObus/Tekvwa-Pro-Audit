"""
Tekvwa Pro Audit - Category Model

Category model for expense/income classification with WREN support.
"""

import uuid
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, ForeignKey, String, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.transaction import Transaction


class CategoryType(str, Enum):
    """Type of category."""
    INCOME = "income"
    EXPENSE = "expense"
    BOTH = "both"


class VATTreatment(str, Enum):
    """VAT treatment for category."""
    STANDARD = "standard"      # 7.5% VAT
    ZERO_RATED = "zero_rated"  # 0% VAT
    EXEMPT = "exempt"          # VAT exempt
    OUT_OF_SCOPE = "out_of_scope"


class Category(BaseModel):
    """
    Category model for expense and income classification.
    
    Includes WREN (Wholly, Reasonably, Exclusively, Necessarily) 
    default flags for tax deductibility classification.
    """
    
    __tablename__ = "categories"
    
    # Basic Info
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Type
    category_type: Mapped[CategoryType] = mapped_column(
        SQLEnum(CategoryType),
        default=CategoryType.EXPENSE,
        nullable=False,
    )
    
    # WREN Classification (for expenses)
    wren_default: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Default WREN tax-deductible status",
    )
    wren_review_required: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Requires manual review for WREN compliance",
    )
    wren_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Notes on WREN classification",
    )
    
    # VAT Treatment
    vat_treatment: Mapped[VATTreatment] = mapped_column(
        SQLEnum(VATTreatment),
        default=VATTreatment.STANDARD,
        nullable=False,
    )
    
    # Hierarchy
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # System category (cannot be deleted)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Relationships
    parent: Mapped[Optional["Category"]] = relationship(
        "Category",
        remote_side="Category.id",
        backref="children",
    )
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction",
        back_populates="category",
        # Explicit foreign_keys required — see the matching note on Transaction.category
        # (app/models/transaction.py) for why this became ambiguous.
        foreign_keys="Transaction.category_id",
    )
    
    def __repr__(self) -> str:
        return f"<Category(id={self.id}, name={self.name}, type={self.category_type})>"
