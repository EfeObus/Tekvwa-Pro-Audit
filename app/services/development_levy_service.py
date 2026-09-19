"""
Tekvwa Pro Audit - Development Levy Service (2026 Reform)

Handles the consolidated 4% Development Levy under the 2026 Act.

The 2026 Nigeria Tax Administration Act consolidates:
- Tertiary Education Tax (TET)
- Police Equipment Fund
- Other levies

Into a SINGLE 4% Development Levy on assessable profit.

Exemption: Companies with turnover <= ₦100M AND fixed assets <= ₦250M
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tax_2026 import DevelopmentLevyRecord
from app.models.entity import BusinessEntity, BusinessType


class DevelopmentLevyService:
    """
    Service for calculating and managing Development Levy.
    
    The Development Levy applies to LIMITED COMPANIES (not Business Names/Sole Proprietors)
    at 4% of assessable profit.
    
    Exemptions (must meet BOTH):
    - Annual turnover <= ₦100,000,000
    - Fixed assets <= ₦250,000,000
    """
    
    LEVY_RATE = Decimal("0.04")  # 4%
    TURNOVER_THRESHOLD = Decimal("100000000")  # ₦100M
    FIXED_ASSETS_THRESHOLD = Decimal("250000000")  # ₦250M
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def calculate_development_levy(
        self,
        entity_id: uuid.UUID,
        fiscal_year: int,
        assessable_profit: Decimal,
        turnover: Optional[Decimal] = None,
        fixed_assets: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """
        Calculate Development Levy for a fiscal year.
        
        Returns calculation details including exemption status.
        """
        # Get entity to check business type
        result = await self.db.execute(
            select(BusinessEntity).where(BusinessEntity.id == entity_id)
        )
        entity = result.scalar_one_or_none()
        
        if not entity:
            raise ValueError("Entity not found")
        
        # Use entity values if not provided
        if turnover is None:
            turnover = entity.annual_turnover or Decimal("0")
        if fixed_assets is None:
            fixed_assets = entity.fixed_assets_value or Decimal("0")
        
        # Check exemption eligibility
        is_exempt = False
        exemption_reason = None
        levy_amount = Decimal("0")
        
        # Business Names (sole proprietors) don't pay Development Levy
        if entity.business_type == BusinessType.BUSINESS_NAME:
            is_exempt = True
            exemption_reason = "Business Names (sole proprietors) are not subject to Development Levy - pay PIT instead"
        # Check small company exemption
        elif turnover <= self.TURNOVER_THRESHOLD and fixed_assets <= self.FIXED_ASSETS_THRESHOLD:
            is_exempt = True
            exemption_reason = f"Small company exemption: Turnover ≤ ₦100M (₦{turnover:,.2f}) AND Fixed Assets ≤ ₦250M (₦{fixed_assets:,.2f})"
        else:
            # Calculate levy
            levy_amount = assessable_profit * self.LEVY_RATE
        
        return {
            "fiscal_year": fiscal_year,
            "assessable_profit": float(assessable_profit),
            "levy_rate": float(self.LEVY_RATE),
            "levy_rate_percentage": f"{float(self.LEVY_RATE) * 100}%",
            "levy_amount": float(levy_amount),
            "is_exempt": is_exempt,
            "exemption_reason": exemption_reason,
            "thresholds": {
                "turnover_threshold": float(self.TURNOVER_THRESHOLD),
                "fixed_assets_threshold": float(self.FIXED_ASSETS_THRESHOLD),
            },
            "entity_values": {
                "turnover": float(turnover),
                "fixed_assets": float(fixed_assets),
                "business_type": entity.business_type.value,
            },
            "note": "Development Levy consolidates TET, Police Fund, and other levies under 2026 Act",
        }
    
    async def save_development_levy_record(
        self,
        entity_id: uuid.UUID,
        fiscal_year: int,
        assessable_profit: Decimal,
        turnover: Optional[Decimal] = None,
        fixed_assets: Optional[Decimal] = None,
    ) -> DevelopmentLevyRecord:
        """
        Save a Development Levy calculation record.
        """
        calculation = await self.calculate_development_levy(
            entity_id, fiscal_year, assessable_profit, turnover, fixed_assets
        )
        
        # Check for existing record
        result = await self.db.execute(
            select(DevelopmentLevyRecord).where(
                and_(
                    DevelopmentLevyRecord.entity_id == entity_id,
                    DevelopmentLevyRecord.fiscal_year == fiscal_year,
                )
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            # Update existing record
            existing.assessable_profit = assessable_profit
            existing.levy_amount = Decimal(str(calculation["levy_amount"]))
            existing.turnover = Decimal(str(calculation["entity_values"]["turnover"]))
            existing.fixed_assets = Decimal(str(calculation["entity_values"]["fixed_assets"]))
            existing.is_exempt = calculation["is_exempt"]
            existing.exemption_reason = calculation["exemption_reason"]
            record = existing
        else:
            # Create new record
            record = DevelopmentLevyRecord(
                entity_id=entity_id,
                fiscal_year=fiscal_year,
                assessable_profit=assessable_profit,
                levy_rate=self.LEVY_RATE,
                levy_amount=Decimal(str(calculation["levy_amount"])),
                turnover=Decimal(str(calculation["entity_values"]["turnover"])),
                fixed_assets=Decimal(str(calculation["entity_values"]["fixed_assets"])),
                is_exempt=calculation["is_exempt"],
                exemption_reason=calculation["exemption_reason"],
            )
            self.db.add(record)
        
        await self.db.commit()
        await self.db.refresh(record)
        
        return record
    
    async def get_development_levy_record(
        self,
        entity_id: uuid.UUID,
        fiscal_year: int,
    ) -> Optional[DevelopmentLevyRecord]:
        """Get Development Levy record for a fiscal year."""
        result = await self.db.execute(
            select(DevelopmentLevyRecord).where(
                and_(
                    DevelopmentLevyRecord.entity_id == entity_id,
                    DevelopmentLevyRecord.fiscal_year == fiscal_year,
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def get_all_records(
        self,
        entity_id: uuid.UUID,
    ) -> List[DevelopmentLevyRecord]:
        """Get all Development Levy records for an entity."""
        result = await self.db.execute(
            select(DevelopmentLevyRecord)
            .where(DevelopmentLevyRecord.entity_id == entity_id)
            .order_by(DevelopmentLevyRecord.fiscal_year.desc())
        )
        return list(result.scalars().all())
    
    async def mark_as_filed(
        self,
        record_id: uuid.UUID,
        payment_reference: Optional[str] = None,
    ) -> DevelopmentLevyRecord:
        """Mark a Development Levy record as filed."""
        result = await self.db.execute(
            select(DevelopmentLevyRecord).where(DevelopmentLevyRecord.id == record_id)
        )
        record = result.scalar_one_or_none()
        
        if not record:
            raise ValueError("Development Levy record not found")
        
        record.is_filed = True
        record.filed_at = datetime.utcnow()
        record.payment_reference = payment_reference
        
        await self.db.commit()
        await self.db.refresh(record)
        
        return record
    
    async def update_entity_thresholds(
        self,
        entity_id: uuid.UUID,
        annual_turnover: Optional[Decimal] = None,
        fixed_assets_value: Optional[Decimal] = None,
    ) -> BusinessEntity:
        """
        Update entity's turnover and fixed assets values.
        
        Also automatically calculates Development Levy exemption status.
        """
        result = await self.db.execute(
            select(BusinessEntity).where(BusinessEntity.id == entity_id)
        )
        entity = result.scalar_one_or_none()
        
        if not entity:
            raise ValueError("Entity not found")
        
        if annual_turnover is not None:
            entity.annual_turnover = annual_turnover
        if fixed_assets_value is not None:
            entity.fixed_assets_value = fixed_assets_value
        
        # Calculate exemption status
        turnover = entity.annual_turnover or Decimal("0")
        assets = entity.fixed_assets_value or Decimal("0")
        
        entity.is_development_levy_exempt = (
            entity.business_type == BusinessType.BUSINESS_NAME or
            (turnover <= self.TURNOVER_THRESHOLD and assets <= self.FIXED_ASSETS_THRESHOLD)
        )
        
        await self.db.commit()
        await self.db.refresh(entity)
        
        return entity
    
    def compare_to_old_regime(
        self,
        assessable_profit: Decimal,
        is_nigerian_company: bool = True,
    ) -> Dict[str, Any]:
        """
        Compare Development Levy to old separate taxes.
        
        Helps users understand the consolidation benefits.
        """
        # Old Tertiary Education Tax was 2.5% (foreign) or 3% (local)
        old_tet_rate = Decimal("0.03") if is_nigerian_company else Decimal("0.025")
        old_tet = assessable_profit * old_tet_rate
        
        # Old Police Equipment Fund was 0.005% of net profit
        old_police_fund = assessable_profit * Decimal("0.00005")
        
        # New consolidated rate
        new_levy = assessable_profit * self.LEVY_RATE
        
        old_total = old_tet + old_police_fund
        savings = old_total - new_levy if old_total > new_levy else Decimal("0")
        increase = new_levy - old_total if new_levy > old_total else Decimal("0")
        
        return {
            "assessable_profit": float(assessable_profit),
            "old_regime": {
                "tertiary_education_tax": float(old_tet),
                "tet_rate": f"{float(old_tet_rate) * 100}%",
                "police_equipment_fund": float(old_police_fund),
                "total": float(old_total),
            },
            "new_regime_2026": {
                "development_levy": float(new_levy),
                "rate": f"{float(self.LEVY_RATE) * 100}%",
            },
            "comparison": {
                "difference": float(new_levy - old_total),
                "savings": float(savings),
                "increase": float(increase),
                "note": "Consolidation simplifies compliance even if amounts similar",
            },
        }
