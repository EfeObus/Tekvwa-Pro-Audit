"""
Tekvwa Pro Audit - WHT Calculator Service

Withholding Tax (WHT) calculation service for Nigerian tax compliance.

WHT Rates (2026):
- Dividends, Interest, Rent: 10%
- Royalties: 10%
- Professional Services: 10% (individual), 5% (company)
- Contract/Supply: 5%
- Consultancy: 5%
- Technical Services: 10%
- Management Fees: 10%
- Director Fees: 10%
- Construction: 5%

WHT is a credit against final tax liability.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Any
from enum import Enum

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession


class WHTServiceType(str, Enum):
    """Types of services/payments subject to WHT."""
    DIVIDENDS = "dividends"
    INTEREST = "interest"
    RENT = "rent"
    ROYALTIES = "royalties"
    PROFESSIONAL_SERVICES = "professional_services"
    CONTRACT_SUPPLY = "contract_supply"
    CONSULTANCY = "consultancy"
    TECHNICAL_SERVICES = "technical_services"
    MANAGEMENT_FEES = "management_fees"
    DIRECTOR_FEES = "director_fees"
    CONSTRUCTION = "construction"
    OTHER = "other"


class PayeeType(str, Enum):
    """Type of payee for WHT calculation."""
    INDIVIDUAL = "individual"
    COMPANY = "company"


# WHT Rates by service type and payee type
WHT_RATES = {
    WHTServiceType.DIVIDENDS: {"individual": Decimal("10"), "company": Decimal("10")},
    WHTServiceType.INTEREST: {"individual": Decimal("10"), "company": Decimal("10")},
    WHTServiceType.RENT: {"individual": Decimal("10"), "company": Decimal("10")},
    WHTServiceType.ROYALTIES: {"individual": Decimal("10"), "company": Decimal("10")},
    WHTServiceType.PROFESSIONAL_SERVICES: {"individual": Decimal("10"), "company": Decimal("5")},
    WHTServiceType.CONTRACT_SUPPLY: {"individual": Decimal("5"), "company": Decimal("5")},
    WHTServiceType.CONSULTANCY: {"individual": Decimal("5"), "company": Decimal("5")},
    WHTServiceType.TECHNICAL_SERVICES: {"individual": Decimal("10"), "company": Decimal("10")},
    WHTServiceType.MANAGEMENT_FEES: {"individual": Decimal("10"), "company": Decimal("10")},
    WHTServiceType.DIRECTOR_FEES: {"individual": Decimal("10"), "company": Decimal("10")},
    WHTServiceType.CONSTRUCTION: {"individual": Decimal("5"), "company": Decimal("5")},
    WHTServiceType.OTHER: {"individual": Decimal("5"), "company": Decimal("5")},
}


class WHTCalculator:
    """
    Withholding Tax (WHT) calculator.
    
    WHT is deducted at source when making payments to vendors/contractors.
    The WHT deducted becomes a tax credit for the recipient.
    """
    
    @staticmethod
    def get_wht_rate(
        service_type: WHTServiceType,
        payee_type: PayeeType = PayeeType.COMPANY,
    ) -> Decimal:
        """
        Get WHT rate for a specific service and payee type.
        
        Args:
            service_type: Type of service/payment
            payee_type: Whether payee is individual or company
            
        Returns:
            WHT rate as percentage
        """
        rates = WHT_RATES.get(service_type, WHT_RATES[WHTServiceType.OTHER])
        return rates.get(payee_type.value, Decimal("5"))
    
    @staticmethod
    def calculate_wht(
        gross_amount: float,
        service_type: WHTServiceType,
        payee_type: PayeeType = PayeeType.COMPANY,
    ) -> Dict[str, Any]:
        """
        Calculate WHT for a payment.
        
        Args:
            gross_amount: The gross payment amount
            service_type: Type of service/payment
            payee_type: Whether payee is individual or company
            
        Returns:
            Dict with WHT calculation details
        """
        gross = Decimal(str(gross_amount))
        rate = WHTCalculator.get_wht_rate(service_type, payee_type)
        
        wht_amount = gross * (rate / 100)
        net_amount = gross - wht_amount
        
        return {
            "gross_amount": float(gross),
            "wht_rate": float(rate),
            "wht_amount": float(round(wht_amount, 2)),
            "net_amount": float(round(net_amount, 2)),
            "service_type": service_type.value,
            "payee_type": payee_type.value,
        }
    
    @staticmethod
    def calculate_gross_from_net(
        net_amount: float,
        service_type: WHTServiceType,
        payee_type: PayeeType = PayeeType.COMPANY,
    ) -> Dict[str, Any]:
        """
        Calculate gross amount from net (when vendor quotes net).
        
        Args:
            net_amount: The net amount vendor wants to receive
            service_type: Type of service/payment
            payee_type: Whether payee is individual or company
            
        Returns:
            Dict with gross calculation details
        """
        net = Decimal(str(net_amount))
        rate = WHTCalculator.get_wht_rate(service_type, payee_type)
        
        # Gross = Net / (1 - rate/100)
        gross = net / (1 - rate / 100)
        wht_amount = gross - net
        
        return {
            "net_amount": float(net),
            "gross_amount": float(round(gross, 2)),
            "wht_rate": float(rate),
            "wht_amount": float(round(wht_amount, 2)),
            "service_type": service_type.value,
            "payee_type": payee_type.value,
        }
    
    @staticmethod
    def get_all_wht_rates() -> List[Dict[str, Any]]:
        """Get all WHT rates for reference."""
        rates = []
        for service_type in WHTServiceType:
            rate_info = WHT_RATES.get(service_type, WHT_RATES[WHTServiceType.OTHER])
            rates.append({
                "service_type": service_type.value,
                "individual_rate": float(rate_info["individual"]),
                "company_rate": float(rate_info["company"]),
            })
        return rates


class WHTService:
    """Service for WHT tracking and management."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.calculator = WHTCalculator()
    
    async def get_wht_summary_for_period(
        self,
        entity_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """
        Get WHT summary for a period.
        
        Calculates total WHT deducted from expense transactions.
        """
        from app.models.transaction import Transaction, TransactionType
        
        result = await self.db.execute(
            select(
                func.count(Transaction.id).label("count"),
                func.coalesce(func.sum(Transaction.wht_amount), 0).label("total_wht"),
                func.coalesce(func.sum(Transaction.amount), 0).label("total_gross"),
            )
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_date >= start_date)
            .where(Transaction.transaction_date <= end_date)
            .where(Transaction.transaction_type == TransactionType.EXPENSE)
            .where(Transaction.wht_amount > 0)
        )
        row = result.one()
        
        return {
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "transaction_count": row.count,
            "total_gross_payments": float(row.total_gross),
            "total_wht_deducted": float(row.total_wht),
        }
    
    async def get_wht_by_vendor(
        self,
        entity_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        """
        Get WHT breakdown by vendor for certificate generation.
        """
        from app.models.transaction import Transaction, TransactionType
        from app.models.vendor import Vendor
        
        result = await self.db.execute(
            select(
                Vendor.id,
                Vendor.name,
                Vendor.tin,
                func.sum(Transaction.amount).label("total_gross"),
                func.sum(Transaction.wht_amount).label("total_wht"),
            )
            .join(Vendor, Transaction.vendor_id == Vendor.id)
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_date >= start_date)
            .where(Transaction.transaction_date <= end_date)
            .where(Transaction.transaction_type == TransactionType.EXPENSE)
            .where(Transaction.wht_amount > 0)
            .group_by(Vendor.id, Vendor.name, Vendor.tin)
        )
        
        vendors = []
        for row in result:
            vendors.append({
                "vendor_id": str(row.id),
                "vendor_name": row.name,
                "vendor_tin": row.tin,
                "total_gross_paid": float(row.total_gross),
                "total_wht_deducted": float(row.total_wht),
            })
        
        return vendors
