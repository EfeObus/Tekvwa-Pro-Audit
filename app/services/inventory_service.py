"""
Tekvwa Pro Audit - Inventory Service

Business logic for inventory management, stock tracking, and write-offs.

GL Integration:
- When inventory is sold, posts COGS: Dr COGS, Cr Inventory
- When inventory is written off, posts: Dr Write-off Expense, Cr Inventory
- When inventory is purchased/received, posts: Dr Inventory, Cr AP (via Transaction)
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inventory import (
    InventoryItem,
    StockMovement,
    StockMovementType,
    StockWriteOff,
    WriteOffReason,
)


# Nigerian Standard COA Account Codes for Inventory
GL_ACCOUNTS = {
    "inventory": "1210",           # Inventory Asset
    "cogs": "5000",                # Cost of Goods Sold
    "writeoff_expense": "5400",    # Inventory Write-off Expense
}


class InventoryService:
    """Service for inventory management."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ===========================================
    # INVENTORY ITEM OPERATIONS
    # ===========================================
    
    async def create_item(
        self,
        entity_id: uuid.UUID,
        sku: str,
        name: str,
        description: Optional[str] = None,
        barcode: Optional[str] = None,
        category: Optional[str] = None,
        unit_cost: float = 0,
        unit_price: float = 0,
        quantity_on_hand: int = 0,
        reorder_level: int = 0,
        reorder_quantity: int = 0,
        unit_of_measure: str = "pcs",
        is_tracked: bool = True,
        created_by: Optional[uuid.UUID] = None,
    ) -> InventoryItem:
        """Create a new inventory item."""
        # Check for duplicate SKU
        existing = await self.get_item_by_sku(entity_id, sku)
        if existing:
            raise ValueError(f"Item with SKU '{sku}' already exists")
        
        item = InventoryItem(
            entity_id=entity_id,
            sku=sku,
            name=name,
            description=description,
            barcode=barcode,
            category=category,
            unit_cost=Decimal(str(unit_cost)),
            unit_price=Decimal(str(unit_price)),
            quantity_on_hand=quantity_on_hand,
            reorder_level=reorder_level,
            reorder_quantity=reorder_quantity,
            unit_of_measure=unit_of_measure,
            is_tracked=is_tracked,
            is_active=True,
        )
        
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        
        # If initial quantity, create a movement
        if quantity_on_hand > 0:
            await self._create_movement(
                item_id=item.id,
                movement_type=StockMovementType.ADJUSTMENT,
                quantity=quantity_on_hand,
                unit_cost=unit_cost,
                reference="Initial stock",
                notes="Initial stock on item creation",
                movement_date=date.today(),
                created_by=created_by,
            )
        
        return item
    
    async def get_item_by_id(
        self,
        item_id: uuid.UUID,
    ) -> Optional[InventoryItem]:
        """Get an inventory item by ID."""
        result = await self.db.execute(
            select(InventoryItem).where(InventoryItem.id == item_id)
        )
        return result.scalar_one_or_none()
    
    async def get_item_by_sku(
        self,
        entity_id: uuid.UUID,
        sku: str,
    ) -> Optional[InventoryItem]:
        """Get an inventory item by SKU."""
        result = await self.db.execute(
            select(InventoryItem)
            .where(InventoryItem.entity_id == entity_id)
            .where(InventoryItem.sku == sku)
        )
        return result.scalar_one_or_none()
    
    async def get_items_for_entity(
        self,
        entity_id: uuid.UUID,
        category: Optional[str] = None,
        is_active: Optional[bool] = None,
        low_stock_only: bool = False,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[InventoryItem], int, int]:
        """
        Get inventory items for an entity.
        
        Returns: (items, total_count, low_stock_count)
        """
        query = select(InventoryItem).where(
            InventoryItem.entity_id == entity_id
        )
        
        if category:
            query = query.where(InventoryItem.category == category)
        
        if is_active is not None:
            query = query.where(InventoryItem.is_active == is_active)
        
        if low_stock_only:
            query = query.where(
                InventoryItem.quantity_on_hand <= InventoryItem.reorder_level
            )
        
        if search:
            search_filter = or_(
                InventoryItem.sku.ilike(f"%{search}%"),
                InventoryItem.name.ilike(f"%{search}%"),
                InventoryItem.barcode.ilike(f"%{search}%"),
            )
            query = query.where(search_filter)
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query) or 0
        
        # Get low stock count
        low_stock_query = select(func.count()).where(
            InventoryItem.entity_id == entity_id,
            InventoryItem.is_active == True,
            InventoryItem.quantity_on_hand <= InventoryItem.reorder_level,
        )
        low_stock_count = await self.db.scalar(low_stock_query) or 0
        
        # Apply pagination
        query = query.order_by(InventoryItem.name).offset(skip).limit(limit)
        
        result = await self.db.execute(query)
        items = list(result.scalars().all())
        
        return items, total, low_stock_count
    
    async def update_item(
        self,
        item_id: uuid.UUID,
        update_data: Dict[str, Any],
    ) -> InventoryItem:
        """Update an inventory item."""
        item = await self.get_item_by_id(item_id)
        if not item:
            raise ValueError("Inventory item not found")
        
        # Handle SKU uniqueness check
        if "sku" in update_data and update_data["sku"] != item.sku:
            existing = await self.get_item_by_sku(item.entity_id, update_data["sku"])
            if existing:
                raise ValueError(f"Item with SKU '{update_data['sku']}' already exists")
        
        for field, value in update_data.items():
            if value is not None and hasattr(item, field):
                if field in ("unit_cost", "unit_price"):
                    value = Decimal(str(value))
                setattr(item, field, value)
        
        await self.db.commit()
        await self.db.refresh(item)
        
        return item
    
    async def delete_item(
        self,
        item_id: uuid.UUID,
    ) -> bool:
        """Delete an inventory item (soft delete by setting inactive)."""
        item = await self.get_item_by_id(item_id)
        if not item:
            raise ValueError("Inventory item not found")
        
        item.is_active = False
        await self.db.commit()
        
        return True
    
    # ===========================================
    # STOCK MOVEMENT OPERATIONS
    # ===========================================
    
    async def _create_movement(
        self,
        item_id: uuid.UUID,
        movement_type: StockMovementType,
        quantity: int,
        unit_cost: float,
        movement_date: date,
        reference: Optional[str] = None,
        notes: Optional[str] = None,
        created_by: Optional[uuid.UUID] = None,
    ) -> StockMovement:
        """Create a stock movement record."""
        movement = StockMovement(
            item_id=item_id,
            movement_type=movement_type,
            quantity=quantity,
            unit_cost=Decimal(str(unit_cost)),
            reference=reference,
            notes=notes,
            movement_date=movement_date,
            created_by=created_by,
        )
        
        self.db.add(movement)
        await self.db.flush()
        
        return movement
    
    async def receive_stock(
        self,
        item_id: uuid.UUID,
        quantity: int,
        unit_cost: float,
        reference: Optional[str] = None,
        notes: Optional[str] = None,
        receive_date: Optional[date] = None,
        created_by: Optional[uuid.UUID] = None,
    ) -> InventoryItem:
        """Receive stock (from purchase)."""
        item = await self.get_item_by_id(item_id)
        if not item:
            raise ValueError("Inventory item not found")
        
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        
        move_date = receive_date or date.today()
        
        # Create movement
        await self._create_movement(
            item_id=item_id,
            movement_type=StockMovementType.PURCHASE,
            quantity=quantity,
            unit_cost=unit_cost,
            reference=reference,
            notes=notes,
            movement_date=move_date,
            created_by=created_by,
        )
        
        # Update stock
        item.quantity_on_hand += quantity
        
        # Update unit cost (weighted average)
        if item.is_tracked:
            old_value = item.unit_cost * (item.quantity_on_hand - quantity)
            new_value = Decimal(str(unit_cost)) * quantity
            item.unit_cost = (old_value + new_value) / item.quantity_on_hand
        
        await self.db.commit()
        await self.db.refresh(item)
        
        return item
    
    async def record_sale(
        self,
        item_id: uuid.UUID,
        quantity: int,
        reference: Optional[str] = None,
        notes: Optional[str] = None,
        sale_date: Optional[date] = None,
        created_by: Optional[uuid.UUID] = None,
        entity_id: Optional[uuid.UUID] = None,
        post_to_gl: bool = True,
    ) -> InventoryItem:
        """
        Record a sale (reduce stock) and post COGS to GL.
        
        GL Journal Entry:
        Dr Cost of Goods Sold (5000)   [quantity x unit_cost]
        Cr Inventory (1210)            [quantity x unit_cost]
        
        Args:
            item_id: Inventory item ID
            quantity: Quantity sold
            reference: Sale reference (invoice number, etc.)
            notes: Additional notes
            sale_date: Date of sale
            created_by: User recording the sale
            entity_id: Business entity ID (needed for GL posting)
            post_to_gl: Whether to post COGS to GL (default True)
        """
        item = await self.get_item_by_id(item_id)
        if not item:
            raise ValueError("Inventory item not found")
        
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        
        if item.is_tracked and quantity > item.quantity_on_hand:
            raise ValueError(f"Insufficient stock. Available: {item.quantity_on_hand}")
        
        move_date = sale_date or date.today()
        
        # Calculate COGS value
        cogs_value = Decimal(str(quantity)) * item.unit_cost
        
        # Create movement (negative quantity for outbound)
        await self._create_movement(
            item_id=item_id,
            movement_type=StockMovementType.SALE,
            quantity=-quantity,
            unit_cost=float(item.unit_cost),
            reference=reference,
            notes=notes,
            movement_date=move_date,
            created_by=created_by,
        )
        
        # Update stock
        item.quantity_on_hand -= quantity
        
        await self.db.commit()
        await self.db.refresh(item)
        
        # Post COGS to GL
        if post_to_gl and created_by:
            # Determine entity_id from item or parameter
            posting_entity_id = entity_id or item.entity_id
            if posting_entity_id:
                try:
                    await self._post_cogs_to_gl(
                        entity_id=posting_entity_id,
                        item=item,
                        quantity=quantity,
                        cogs_value=cogs_value,
                        reference=reference or f"SALE-{str(item.id)[:8]}",
                        sale_date=move_date,
                        user_id=created_by,
                    )
                except Exception as e:
                    import logging
                    logging.error(f"GL posting failed for inventory sale {item.id}: {e}")
        
        return item
    
    async def _get_gl_account_id(
        self,
        entity_id: uuid.UUID,
        account_code: str,
    ) -> Optional[uuid.UUID]:
        """Get GL account ID by account code."""
        from app.models.accounting import ChartOfAccounts
        
        result = await self.db.execute(
            select(ChartOfAccounts.id)
            .where(ChartOfAccounts.entity_id == entity_id)
            .where(ChartOfAccounts.account_code == account_code)
            .where(ChartOfAccounts.is_active == True)
        )
        account = result.scalar_one_or_none()
        return account
    
    async def _post_cogs_to_gl(
        self,
        entity_id: uuid.UUID,
        item: InventoryItem,
        quantity: int,
        cogs_value: Decimal,
        reference: str,
        sale_date: date,
        user_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Post Cost of Goods Sold to General Ledger.
        
        Journal Entry:
        Dr Cost of Goods Sold (5000)   [cogs_value]
        Cr Inventory (1210)            [cogs_value]
        """
        from app.services.accounting_service import AccountingService
        from app.schemas.accounting import GLPostingRequest, JournalEntryLineCreate
        
        accounting_service = AccountingService(self.db)
        
        # Build journal lines
        lines = []
        
        # Debit: COGS
        cogs_account_id = await self._get_gl_account_id(entity_id, GL_ACCOUNTS["cogs"])
        if cogs_account_id:
            lines.append(JournalEntryLineCreate(
                account_id=cogs_account_id,
                debit_amount=cogs_value,
                credit_amount=Decimal("0"),
                description=f"COGS: {quantity}x {item.name}",
            ))
        
        # Credit: Inventory
        inventory_account_id = await self._get_gl_account_id(entity_id, GL_ACCOUNTS["inventory"])
        if inventory_account_id:
            lines.append(JournalEntryLineCreate(
                account_id=inventory_account_id,
                debit_amount=Decimal("0"),
                credit_amount=cogs_value,
                description=f"Inventory reduction: {quantity}x {item.name}",
            ))
        
        if not lines:
            return {"success": False, "error": "No GL accounts found for COGS posting"}
        
        # Create GL posting request
        gl_request = GLPostingRequest(
            entry_date=sale_date,
            reference=reference,
            description=f"COGS for {item.name} ({quantity} units)",
            source_document_type="inventory_sale",
            source_document_id=str(item.id),
            lines=lines,
        )
        
        # Post to GL
        result = await accounting_service.post_to_gl(entity_id, gl_request, user_id)
        
        return {
            "success": result.success,
            "journal_entry_id": str(result.journal_entry_id) if result.journal_entry_id else None,
            "message": result.message,
        }
    
    async def _post_writeoff_to_gl(
        self,
        entity_id: uuid.UUID,
        item: InventoryItem,
        quantity: int,
        writeoff_value: Decimal,
        reference: str,
        writeoff_date: date,
        user_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Post inventory write-off to General Ledger.
        
        Journal Entry:
        Dr Write-off Expense (5400)    [writeoff_value]
        Cr Inventory (1210)            [writeoff_value]
        """
        from app.services.accounting_service import AccountingService
        from app.schemas.accounting import GLPostingRequest, JournalEntryLineCreate
        
        accounting_service = AccountingService(self.db)
        
        # Build journal lines
        lines = []
        
        # Debit: Write-off Expense
        writeoff_account_id = await self._get_gl_account_id(entity_id, GL_ACCOUNTS["writeoff_expense"])
        if writeoff_account_id:
            lines.append(JournalEntryLineCreate(
                account_id=writeoff_account_id,
                debit_amount=writeoff_value,
                credit_amount=Decimal("0"),
                description=f"Inventory write-off: {quantity}x {item.name}",
            ))
        
        # Credit: Inventory
        inventory_account_id = await self._get_gl_account_id(entity_id, GL_ACCOUNTS["inventory"])
        if inventory_account_id:
            lines.append(JournalEntryLineCreate(
                account_id=inventory_account_id,
                debit_amount=Decimal("0"),
                credit_amount=writeoff_value,
                description=f"Write-off: {quantity}x {item.name}",
            ))
        
        if not lines:
            return {"success": False, "error": "No GL accounts found for write-off posting"}
        
        # Create GL posting request
        gl_request = GLPostingRequest(
            entry_date=writeoff_date,
            reference=reference,
            description=f"Inventory write-off: {item.name} ({quantity} units)",
            source_document_type="inventory_writeoff",
            source_document_id=str(item.id),
            lines=lines,
        )
        
        # Post to GL
        result = await accounting_service.post_to_gl(entity_id, gl_request, user_id)
        
        return {
            "success": result.success,
            "journal_entry_id": str(result.journal_entry_id) if result.journal_entry_id else None,
            "message": result.message,
        }
    
    async def adjust_stock(
        self,
        item_id: uuid.UUID,
        quantity_change: int,
        reason: str,
        reference: Optional[str] = None,
        adjustment_date: Optional[date] = None,
        created_by: Optional[uuid.UUID] = None,
    ) -> InventoryItem:
        """Adjust stock (positive or negative)."""
        item = await self.get_item_by_id(item_id)
        if not item:
            raise ValueError("Inventory item not found")
        
        new_quantity = item.quantity_on_hand + quantity_change
        if new_quantity < 0:
            raise ValueError(f"Adjustment would result in negative stock ({new_quantity})")
        
        move_date = adjustment_date or date.today()
        
        await self._create_movement(
            item_id=item_id,
            movement_type=StockMovementType.ADJUSTMENT,
            quantity=quantity_change,
            unit_cost=float(item.unit_cost),
            reference=reference,
            notes=reason,
            movement_date=move_date,
            created_by=created_by,
        )
        
        item.quantity_on_hand = new_quantity
        
        await self.db.commit()
        await self.db.refresh(item)
        
        return item
    
    async def get_movements_for_item(
        self,
        item_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        movement_type: Optional[StockMovementType] = None,
        limit: int = 100,
    ) -> List[StockMovement]:
        """Get stock movements for an item."""
        query = select(StockMovement).where(StockMovement.item_id == item_id)
        
        if start_date:
            query = query.where(StockMovement.movement_date >= start_date)
        if end_date:
            query = query.where(StockMovement.movement_date <= end_date)
        if movement_type:
            query = query.where(StockMovement.movement_type == movement_type)
        
        query = query.order_by(StockMovement.movement_date.desc()).limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    # ===========================================
    # WRITE-OFF OPERATIONS
    # ===========================================
    
    async def create_write_off(
        self,
        item_id: uuid.UUID,
        quantity: int,
        reason: str,
        notes: Optional[str] = None,
        documentation_url: Optional[str] = None,
        write_off_date: Optional[date] = None,
        is_tax_deductible: bool = True,
        created_by: Optional[uuid.UUID] = None,
        entity_id: Optional[uuid.UUID] = None,
        post_to_gl: bool = True,
    ) -> StockWriteOff:
        """
        Create a stock write-off and post to GL.
        
        GL Journal Entry:
        Dr Write-off Expense (5400)    [total_value]
        Cr Inventory (1210)            [total_value]
        
        Args:
            item_id: Inventory item ID
            quantity: Quantity to write off
            reason: Write-off reason (damage, obsolete, etc.)
            notes: Additional notes
            documentation_url: Supporting documentation URL
            write_off_date: Date of write-off
            is_tax_deductible: Whether write-off is tax deductible
            created_by: User creating the write-off
            entity_id: Business entity ID (for GL posting)
            post_to_gl: Whether to post to GL (default True)
        """
        item = await self.get_item_by_id(item_id)
        if not item:
            raise ValueError("Inventory item not found")
        
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        
        if item.is_tracked and quantity > item.quantity_on_hand:
            raise ValueError(f"Cannot write off more than available. Stock: {item.quantity_on_hand}")
        
        try:
            write_off_reason = WriteOffReason(reason)
        except ValueError:
            write_off_reason = WriteOffReason.OTHER
        
        wo_date = write_off_date or date.today()
        total_value = item.unit_cost * quantity
        
        # Create write-off record
        write_off = StockWriteOff(
            item_id=item_id,
            quantity=quantity,
            unit_cost=item.unit_cost,
            total_value=total_value,
            reason=write_off_reason,
            notes=notes,
            documentation_url=documentation_url,
            write_off_date=wo_date,
            is_tax_deductible=is_tax_deductible,
            reviewed=False,
            created_by=created_by,
        )
        
        self.db.add(write_off)
        
        # Create movement
        await self._create_movement(
            item_id=item_id,
            movement_type=StockMovementType.WRITE_OFF,
            quantity=-quantity,
            unit_cost=float(item.unit_cost),
            reference=f"Write-off: {reason}",
            notes=notes,
            movement_date=wo_date,
            created_by=created_by,
        )
        
        # Update stock
        item.quantity_on_hand -= quantity
        
        await self.db.commit()
        await self.db.refresh(write_off)
        
        # Post to GL
        if post_to_gl and created_by:
            posting_entity_id = entity_id or item.entity_id
            if posting_entity_id:
                try:
                    await self._post_writeoff_to_gl(
                        entity_id=posting_entity_id,
                        item=item,
                        quantity=quantity,
                        writeoff_value=total_value,
                        reference=f"WO-{str(write_off.id)[:8]}",
                        writeoff_date=wo_date,
                        user_id=created_by,
                    )
                except Exception as e:
                    import logging
                    logging.error(f"GL posting failed for write-off {write_off.id}: {e}")
        
        return write_off
    
    async def get_write_offs_for_entity(
        self,
        entity_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        reviewed: Optional[bool] = None,
        is_tax_deductible: Optional[bool] = None,
    ) -> List[StockWriteOff]:
        """Get write-offs for an entity."""
        query = (
            select(StockWriteOff)
            .join(InventoryItem)
            .where(InventoryItem.entity_id == entity_id)
        )
        
        if start_date:
            query = query.where(StockWriteOff.write_off_date >= start_date)
        if end_date:
            query = query.where(StockWriteOff.write_off_date <= end_date)
        if reviewed is not None:
            query = query.where(StockWriteOff.reviewed == reviewed)
        if is_tax_deductible is not None:
            query = query.where(StockWriteOff.is_tax_deductible == is_tax_deductible)
        
        query = query.order_by(StockWriteOff.write_off_date.desc())
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def review_write_off(
        self,
        write_off_id: uuid.UUID,
        is_tax_deductible: bool,
        notes: Optional[str] = None,
    ) -> StockWriteOff:
        """Review a write-off (accountant/auditor approval)."""
        result = await self.db.execute(
            select(StockWriteOff).where(StockWriteOff.id == write_off_id)
        )
        write_off = result.scalar_one_or_none()
        
        if not write_off:
            raise ValueError("Write-off not found")
        
        write_off.is_tax_deductible = is_tax_deductible
        write_off.reviewed = True
        write_off.reviewed_at = datetime.utcnow()
        
        if notes:
            existing_notes = write_off.notes or ""
            write_off.notes = f"{existing_notes}\n[Review] {notes}".strip()
        
        await self.db.commit()
        await self.db.refresh(write_off)
        
        return write_off
    
    # ===========================================
    # REPORTS
    # ===========================================
    
    async def get_inventory_summary(
        self,
        entity_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Get inventory summary for an entity."""
        # Total counts
        result = await self.db.execute(
            select(
                func.count(InventoryItem.id).label("total"),
                func.count(InventoryItem.id).filter(InventoryItem.is_active == True).label("active"),
                func.count(InventoryItem.id).filter(InventoryItem.is_active == False).label("inactive"),
                func.coalesce(func.sum(InventoryItem.quantity_on_hand), 0).label("total_qty"),
                func.coalesce(
                    func.sum(InventoryItem.quantity_on_hand * InventoryItem.unit_cost), 0
                ).label("total_value"),
            )
            .where(InventoryItem.entity_id == entity_id)
        )
        row = result.one()
        
        # Low stock count
        low_stock = await self.db.scalar(
            select(func.count())
            .where(InventoryItem.entity_id == entity_id)
            .where(InventoryItem.is_active == True)
            .where(InventoryItem.quantity_on_hand <= InventoryItem.reorder_level)
        ) or 0
        
        # Out of stock count
        out_of_stock = await self.db.scalar(
            select(func.count())
            .where(InventoryItem.entity_id == entity_id)
            .where(InventoryItem.is_active == True)
            .where(InventoryItem.quantity_on_hand == 0)
        ) or 0
        
        return {
            "total_items": row.total,
            "active_items": row.active,
            "inactive_items": row.inactive,
            "total_quantity": int(row.total_qty),
            "total_stock_value": float(row.total_value),
            "low_stock_count": low_stock,
            "out_of_stock_count": out_of_stock,
        }
    
    async def get_low_stock_alerts(
        self,
        entity_id: uuid.UUID,
    ) -> List[Dict[str, Any]]:
        """Get items with low stock."""
        result = await self.db.execute(
            select(InventoryItem)
            .where(InventoryItem.entity_id == entity_id)
            .where(InventoryItem.is_active == True)
            .where(InventoryItem.quantity_on_hand <= InventoryItem.reorder_level)
            .order_by(InventoryItem.quantity_on_hand)
        )
        
        alerts = []
        for item in result.scalars():
            alerts.append({
                "item_id": str(item.id),
                "sku": item.sku,
                "name": item.name,
                "quantity_on_hand": item.quantity_on_hand,
                "reorder_level": item.reorder_level,
                "reorder_quantity": item.reorder_quantity,
            })
        
        return alerts
    
    async def get_inventory_valuation(
        self,
        entity_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Get inventory valuation report."""
        result = await self.db.execute(
            select(InventoryItem)
            .where(InventoryItem.entity_id == entity_id)
            .where(InventoryItem.is_active == True)
            .where(InventoryItem.quantity_on_hand > 0)
            .order_by(InventoryItem.name)
        )
        
        items = list(result.scalars().all())
        
        total_cost = sum(item.stock_value for item in items)
        total_price = sum(item.unit_price * item.quantity_on_hand for item in items)
        total_qty = sum(item.quantity_on_hand for item in items)
        
        return {
            "valuation_date": date.today().isoformat(),
            "total_items": len(items),
            "total_quantity": total_qty,
            "total_value_at_cost": float(total_cost),
            "total_value_at_price": float(total_price),
            "potential_profit": float(total_price - total_cost),
            "items": items,
        }
