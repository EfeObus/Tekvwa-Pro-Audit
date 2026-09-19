"""
Tekvwa Pro Audit - PIT Relief Document Service (2026 Reform)

Handles the Personal Income Tax relief document management under 2026 reforms.

The 2026 Nigeria Tax Administration Act ABOLISHED the Consolidated Relief Allowance (CRA)
and replaced it with specific, document-backed reliefs:

- Rent Relief: 20% of rent paid (capped at ₦500,000)
- Life Insurance Premium
- National Housing Fund (NHF) Contribution
- Pension Contribution
- NHIS Contribution
- Gratuity

NRS now requires digital proof for each relief claim.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tax_2026 import PITReliefDocument, ReliefType, ReliefStatus
from app.models.entity import BusinessEntity, BusinessType
from app.services.file_storage_service import FileStorageService


class PITReliefService:
    """
    Service for managing PIT Relief Documents.
    
    Under the 2026 reforms, employees and sole proprietors
    must provide documentary evidence for each tax relief claim.
    
    Relief Caps and Rules:
    - Rent: 20% of annual rent, max ₦500,000
    - Life Insurance: Actual premium paid
    - NHF: 2.5% of basic salary
    - Pension: Up to 8% of basic salary
    - NHIS: Actual contribution
    - Gratuity: As per employment terms
    """
    
    RENT_RELIEF_PERCENTAGE = Decimal("0.20")  # 20%
    RENT_RELIEF_CAP = Decimal("500000")  # ₦500,000
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.file_storage = FileStorageService()
    
    async def create_relief_document(
        self,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        relief_type: ReliefType,
        fiscal_year: int,
        claimed_amount: Decimal,
        annual_rent: Optional[Decimal] = None,
        document_url: Optional[str] = None,
        document_name: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> PITReliefDocument:
        """
        Create a new PIT relief document.
        
        Automatically calculates allowed amount based on relief type and caps.
        """
        # Calculate allowed amount
        allowed_amount = self._calculate_allowed_amount(
            relief_type, claimed_amount, annual_rent
        )
        
        document = PITReliefDocument(
            entity_id=entity_id,
            user_id=user_id,
            relief_type=relief_type,
            fiscal_year=fiscal_year,
            claimed_amount=claimed_amount,
            allowed_amount=allowed_amount,
            annual_rent=annual_rent,
            rent_relief_cap=self.RENT_RELIEF_CAP if relief_type == ReliefType.RENT else None,
            document_url=document_url,
            document_name=document_name,
            document_type=document_type,
            status=ReliefStatus.PENDING,
        )
        
        self.db.add(document)
        await self.db.commit()
        await self.db.refresh(document)
        
        return document
    
    def _calculate_allowed_amount(
        self,
        relief_type: ReliefType,
        claimed_amount: Decimal,
        annual_rent: Optional[Decimal] = None,
    ) -> Decimal:
        """Calculate the allowed relief amount based on type and caps."""
        if relief_type == ReliefType.RENT:
            if annual_rent is None:
                return Decimal("0")
            # 20% of rent, capped at ₦500,000
            rent_relief = annual_rent * self.RENT_RELIEF_PERCENTAGE
            return min(rent_relief, self.RENT_RELIEF_CAP)
        else:
            # Other reliefs: full amount claimed (subject to verification)
            return claimed_amount
    
    async def upload_document(
        self,
        relief_id: uuid.UUID,
        file_content: bytes,
        filename: str,
        content_type: str,
    ) -> PITReliefDocument:
        """Upload supporting document for a relief claim."""
        result = await self.db.execute(
            select(PITReliefDocument).where(PITReliefDocument.id == relief_id)
        )
        document = result.scalar_one_or_none()
        
        if not document:
            raise ValueError("Relief document not found")
        
        # Upload to storage
        url = await self.file_storage.upload_file(
            file_content=file_content,
            filename=f"reliefs/{document.fiscal_year}/{document.id}/{filename}",
            content_type=content_type,
        )
        
        document.document_url = url
        document.document_name = filename
        document.document_type = content_type.split("/")[-1].upper()
        
        await self.db.commit()
        await self.db.refresh(document)
        
        return document
    
    async def verify_relief(
        self,
        relief_id: uuid.UUID,
        verified_by: uuid.UUID,
        approved: bool,
        notes: Optional[str] = None,
    ) -> PITReliefDocument:
        """Verify/review a relief document."""
        result = await self.db.execute(
            select(PITReliefDocument).where(PITReliefDocument.id == relief_id)
        )
        document = result.scalar_one_or_none()
        
        if not document:
            raise ValueError("Relief document not found")
        
        document.is_verified = True
        document.verified_at = datetime.utcnow()
        document.verified_by = verified_by
        document.verification_notes = notes
        document.status = ReliefStatus.APPROVED if approved else ReliefStatus.REJECTED
        
        await self.db.commit()
        await self.db.refresh(document)
        
        return document
    
    async def get_user_reliefs(
        self,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        fiscal_year: Optional[int] = None,
    ) -> List[PITReliefDocument]:
        """Get all relief documents for a user."""
        query = select(PITReliefDocument).where(
            and_(
                PITReliefDocument.entity_id == entity_id,
                PITReliefDocument.user_id == user_id,
            )
        )
        
        if fiscal_year:
            query = query.where(PITReliefDocument.fiscal_year == fiscal_year)
        
        query = query.order_by(PITReliefDocument.fiscal_year.desc(), PITReliefDocument.created_at.desc())
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_relief_summary(
        self,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        fiscal_year: int,
    ) -> Dict[str, Any]:
        """Get relief summary for a user in a fiscal year."""
        result = await self.db.execute(
            select(
                PITReliefDocument.relief_type,
                PITReliefDocument.status,
                func.sum(PITReliefDocument.claimed_amount).label("claimed"),
                func.sum(PITReliefDocument.allowed_amount).label("allowed"),
                func.count(PITReliefDocument.id).label("count"),
            )
            .where(
                and_(
                    PITReliefDocument.entity_id == entity_id,
                    PITReliefDocument.user_id == user_id,
                    PITReliefDocument.fiscal_year == fiscal_year,
                )
            )
            .group_by(PITReliefDocument.relief_type, PITReliefDocument.status)
        )
        
        rows = result.all()
        
        by_type = {}
        total_claimed = Decimal("0")
        total_allowed = Decimal("0")
        total_approved = Decimal("0")
        
        for row in rows:
            relief_type, status, claimed, allowed, count = row
            
            if relief_type.value not in by_type:
                by_type[relief_type.value] = {
                    "claimed": Decimal("0"),
                    "allowed": Decimal("0"),
                    "approved": Decimal("0"),
                    "pending": Decimal("0"),
                    "rejected": Decimal("0"),
                    "documents": 0,
                }
            
            by_type[relief_type.value]["claimed"] += claimed
            by_type[relief_type.value]["allowed"] += allowed or Decimal("0")
            by_type[relief_type.value]["documents"] += count
            
            if status == ReliefStatus.APPROVED:
                by_type[relief_type.value]["approved"] += allowed or Decimal("0")
                total_approved += allowed or Decimal("0")
            elif status == ReliefStatus.PENDING:
                by_type[relief_type.value]["pending"] += allowed or Decimal("0")
            elif status == ReliefStatus.REJECTED:
                by_type[relief_type.value]["rejected"] += claimed
            
            total_claimed += claimed
            total_allowed += allowed or Decimal("0")
        
        # Convert to JSON-serializable
        for key in by_type:
            by_type[key] = {k: float(v) if isinstance(v, Decimal) else v for k, v in by_type[key].items()}
        
        return {
            "fiscal_year": fiscal_year,
            "total_claimed": float(total_claimed),
            "total_allowed": float(total_allowed),
            "total_approved": float(total_approved),
            "by_type": by_type,
            "cra_abolished_note": "CRA was abolished under 2026 reforms. Document-backed reliefs only.",
        }
    
    async def get_entity_reliefs(
        self,
        entity_id: uuid.UUID,
        fiscal_year: int,
        status: Optional[ReliefStatus] = None,
    ) -> List[PITReliefDocument]:
        """Get all relief documents for an entity (all employees)."""
        query = select(PITReliefDocument).where(
            and_(
                PITReliefDocument.entity_id == entity_id,
                PITReliefDocument.fiscal_year == fiscal_year,
            )
        )
        
        if status:
            query = query.where(PITReliefDocument.status == status)
        
        query = query.order_by(PITReliefDocument.created_at.desc())
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_pending_verifications(
        self,
        entity_id: uuid.UUID,
    ) -> List[PITReliefDocument]:
        """Get all pending relief documents requiring verification."""
        result = await self.db.execute(
            select(PITReliefDocument)
            .where(
                and_(
                    PITReliefDocument.entity_id == entity_id,
                    PITReliefDocument.status == ReliefStatus.PENDING,
                )
            )
            .order_by(PITReliefDocument.created_at.asc())
        )
        return list(result.scalars().all())
    
    def get_relief_types_info(self) -> Dict[str, Any]:
        """Get information about available relief types."""
        return {
            "relief_types": [
                {
                    "type": ReliefType.RENT.value,
                    "name": "Rent Relief",
                    "description": "20% of annual rent paid",
                    "cap": float(self.RENT_RELIEF_CAP),
                    "cap_formatted": "₦500,000",
                    "required_documents": ["Rent receipt", "Tenancy agreement"],
                },
                {
                    "type": ReliefType.LIFE_INSURANCE.value,
                    "name": "Life Insurance Premium",
                    "description": "Actual premium paid on life insurance policy",
                    "cap": None,
                    "required_documents": ["Insurance premium receipt", "Policy document"],
                },
                {
                    "type": ReliefType.NHF.value,
                    "name": "National Housing Fund",
                    "description": "2.5% of basic salary contribution to NHF",
                    "cap": None,
                    "required_documents": ["NHF contribution statement"],
                },
                {
                    "type": ReliefType.PENSION.value,
                    "name": "Pension Contribution",
                    "description": "Employee contribution to approved pension scheme",
                    "cap": "8% of basic salary",
                    "required_documents": ["Pension contribution statement", "RSA statement"],
                },
                {
                    "type": ReliefType.NHIS.value,
                    "name": "National Health Insurance",
                    "description": "Contribution to NHIS scheme",
                    "cap": None,
                    "required_documents": ["NHIS contribution receipt"],
                },
                {
                    "type": ReliefType.GRATUITY.value,
                    "name": "Gratuity",
                    "description": "Gratuity contribution as per employment terms",
                    "cap": None,
                    "required_documents": ["Employment contract", "Gratuity contribution statement"],
                },
            ],
            "2026_reform_note": "The CRA (Consolidated Relief Allowance) was abolished. All reliefs now require documentary proof.",
        }
