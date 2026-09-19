"""
Tekvwa Pro Audit - Foreign Exchange (FX) Service

Comprehensive multi-currency support including:
- Exchange rate management with Redis caching
- FX gain/loss calculation (realized and unrealized)
- Period-end revaluation
- FX exposure reporting
- IAS 21 compliance for Nigerian businesses

Author: Tekvwa Pro Audit Team
Date: January 2026
"""

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple, Dict, Any

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounting import (
    ChartOfAccounts, AccountType, AccountSubType, NormalBalance,
    JournalEntry, JournalEntryLine, JournalEntryStatus, JournalEntryType,
    FiscalPeriod, FiscalPeriodStatus,
    FXRevaluation, FXRevaluationType, FXAccountType, FXExposureSummary,
)
from app.models.sku import ExchangeRate
from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)


class FXService:
    """Service for foreign exchange operations."""
    
    # Standard FX gain/loss account codes (Nigerian standard)
    FX_GAIN_ACCOUNT_CODE = "7100"  # Other Income - FX Gain
    FX_LOSS_ACCOUNT_CODE = "8100"  # Other Expense - FX Loss
    UNREALIZED_FX_GAIN_ACCOUNT_CODE = "7110"  # Unrealized FX Gain
    UNREALIZED_FX_LOSS_ACCOUNT_CODE = "8110"  # Unrealized FX Loss
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # =========================================================================
    # EXCHANGE RATE MANAGEMENT
    # =========================================================================
    
    async def get_exchange_rate(
        self,
        from_currency: str,
        to_currency: str,
        rate_date: Optional[date] = None,
        use_cache: bool = True,
    ) -> Optional[Decimal]:
        """
        Get exchange rate for a currency pair.
        Uses the closest available rate on or before the date.
        Implements Redis caching for performance.
        """
        if from_currency == to_currency:
            return Decimal("1.000000")
        
        if rate_date is None:
            rate_date = date.today()
        
        # Try cache first
        if use_cache:
            cache = get_cache_service()
            cached_rate = await cache.get_fx_rate(from_currency, to_currency, rate_date)
            if cached_rate is not None:
                logger.debug(f"Cache hit for FX rate {from_currency}/{to_currency}")
                return cached_rate
        
        # Query database
        result = await self.db.execute(
            select(ExchangeRate)
            .where(and_(
                ExchangeRate.from_currency == from_currency,
                ExchangeRate.to_currency == to_currency,
                ExchangeRate.rate_date <= rate_date,
            ))
            .order_by(ExchangeRate.rate_date.desc())
            .limit(1)
        )
        rate_record = result.scalar_one_or_none()
        
        if rate_record:
            rate = rate_record.rate
            # Cache the result
            if use_cache:
                await cache.set_fx_rate(from_currency, to_currency, rate_date, rate)
            return rate
        
        # Try reverse rate
        result = await self.db.execute(
            select(ExchangeRate)
            .where(and_(
                ExchangeRate.from_currency == to_currency,
                ExchangeRate.to_currency == from_currency,
                ExchangeRate.rate_date <= rate_date,
            ))
            .order_by(ExchangeRate.rate_date.desc())
            .limit(1)
        )
        reverse_rate = result.scalar_one_or_none()
        
        if reverse_rate and reverse_rate.rate > 0:
            rate = Decimal("1") / reverse_rate.rate
            # Cache the calculated rate
            if use_cache:
                await cache.set_fx_rate(from_currency, to_currency, rate_date, rate)
            return rate
        
        return None
    
    async def get_all_exchange_rates(
        self,
        base_currency: str = "NGN",
        rate_date: Optional[date] = None,
        use_cache: bool = True,
    ) -> Dict[str, Decimal]:
        """Get all exchange rates to base currency with caching."""
        if rate_date is None:
            rate_date = date.today()
        
        # Try cache first
        if use_cache:
            cache = get_cache_service()
            cached_rates = await cache.get_all_fx_rates(base_currency, rate_date)
            if cached_rates is not None:
                logger.debug(f"Cache hit for all FX rates to {base_currency}")
                return cached_rates
        
        rates = {}
        
        result = await self.db.execute(
            select(ExchangeRate)
            .where(and_(
                ExchangeRate.to_currency == base_currency,
                ExchangeRate.rate_date <= rate_date,
            ))
            .order_by(ExchangeRate.from_currency, ExchangeRate.rate_date.desc())
        )
        
        for rate in result.scalars().all():
            if rate.from_currency not in rates:
                rates[rate.from_currency] = rate.rate
        
        # Cache the result
        if use_cache and rates:
            await cache.set_all_fx_rates(base_currency, rate_date, rates)
        
        return rates
    
    async def update_exchange_rate(
        self,
        from_currency: str,
        to_currency: str,
        rate: Decimal,
        rate_date: date,
        source: str = "manual",
        is_billing_rate: bool = False,
    ) -> ExchangeRate:
        """Add or update an exchange rate. Invalidates cache on update."""
        # Check if rate exists for this date
        result = await self.db.execute(
            select(ExchangeRate)
            .where(and_(
                ExchangeRate.from_currency == from_currency,
                ExchangeRate.to_currency == to_currency,
                ExchangeRate.rate_date == rate_date,
            ))
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            existing.rate = rate
            existing.source = source
            existing.is_billing_rate = is_billing_rate
            await self.db.commit()
            # Invalidate cache for this currency pair
            cache = get_cache_service()
            await cache.invalidate_fx_rates(from_currency, to_currency)
            return existing
        
        new_rate = ExchangeRate(
            from_currency=from_currency,
            to_currency=to_currency,
            rate=rate,
            rate_date=rate_date,
            source=source,
            is_billing_rate=is_billing_rate,
        )
        self.db.add(new_rate)
        await self.db.commit()
        await self.db.refresh(new_rate)
        # Invalidate cache for this currency pair (new rate may affect lookups)
        cache = get_cache_service()
        await cache.invalidate_fx_rates(from_currency, to_currency)
        return new_rate
    
    # =========================================================================
    # CURRENCY CONVERSION
    # =========================================================================
    
    async def convert_amount(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        rate_date: Optional[date] = None,
        exchange_rate: Optional[Decimal] = None,
    ) -> Tuple[Decimal, Decimal]:
        """
        Convert amount from one currency to another.
        
        Returns:
            Tuple of (converted_amount, exchange_rate_used)
        """
        if from_currency == to_currency:
            return amount, Decimal("1.000000")
        
        if exchange_rate is None:
            exchange_rate = await self.get_exchange_rate(
                from_currency, to_currency, rate_date
            )
            if exchange_rate is None:
                raise ValueError(
                    f"No exchange rate found for {from_currency}/{to_currency}"
                )
        
        converted = (amount * exchange_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return converted, exchange_rate
    
    # =========================================================================
    # FX EXPOSURE TRACKING
    # =========================================================================
    
    async def get_fx_accounts(
        self,
        entity_id: uuid.UUID,
    ) -> List[ChartOfAccounts]:
        """Get all accounts with foreign currency exposure."""
        result = await self.db.execute(
            select(ChartOfAccounts)
            .where(and_(
                ChartOfAccounts.entity_id == entity_id,
                ChartOfAccounts.is_active == True,
                ChartOfAccounts.currency != "NGN",
            ))
            .order_by(ChartOfAccounts.account_code)
        )
        return list(result.scalars().all())
    
    async def get_fx_exposure_by_currency(
        self,
        entity_id: uuid.UUID,
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get FX exposure summary by currency.
        
        Returns exposure broken down by:
        - Bank accounts (domiciliary)
        - Receivables
        - Payables
        - Net exposure
        """
        if as_of_date is None:
            as_of_date = date.today()
        
        exposures = {}
        
        # Get all FX accounts with their balances
        result = await self.db.execute(
            select(ChartOfAccounts)
            .where(and_(
                ChartOfAccounts.entity_id == entity_id,
                ChartOfAccounts.is_active == True,
                ChartOfAccounts.currency != "NGN",
                ChartOfAccounts.is_header == False,
            ))
        )
        
        for account in result.scalars().all():
            currency = account.currency
            if currency not in exposures:
                exposures[currency] = {
                    "currency": currency,
                    "bank_balance": Decimal("0.00"),
                    "receivable_balance": Decimal("0.00"),
                    "payable_balance": Decimal("0.00"),
                    "loan_balance": Decimal("0.00"),
                    "net_asset_exposure": Decimal("0.00"),
                    "net_liability_exposure": Decimal("0.00"),
                    "current_rate": None,
                    "ngn_equivalent": Decimal("0.00"),
                    "accounts": [],
                }
            
            balance = account.current_balance or Decimal("0.00")
            
            # Categorize by account sub-type
            if account.account_sub_type == AccountSubType.BANK:
                exposures[currency]["bank_balance"] += balance
            elif account.account_sub_type == AccountSubType.ACCOUNTS_RECEIVABLE:
                exposures[currency]["receivable_balance"] += balance
            elif account.account_sub_type == AccountSubType.ACCOUNTS_PAYABLE:
                exposures[currency]["payable_balance"] += balance
            elif account.account_sub_type == AccountSubType.LOAN:
                exposures[currency]["loan_balance"] += balance
            
            if account.account_type in [AccountType.ASSET]:
                exposures[currency]["net_asset_exposure"] += balance
            elif account.account_type in [AccountType.LIABILITY]:
                exposures[currency]["net_liability_exposure"] += balance
            
            exposures[currency]["accounts"].append({
                "account_code": account.account_code,
                "account_name": account.account_name,
                "account_type": account.account_type.value,
                "balance": float(balance),
            })
        
        # Get current rates and calculate NGN equivalents
        for currency, data in exposures.items():
            rate = await self.get_exchange_rate(currency, "NGN", as_of_date)
            if rate:
                data["current_rate"] = float(rate)
                net_fc = (
                    data["bank_balance"] + 
                    data["receivable_balance"] - 
                    data["payable_balance"] - 
                    data["loan_balance"]
                )
                data["net_fc_exposure"] = float(net_fc)
                data["ngn_equivalent"] = float(net_fc * rate)
        
        return exposures
    
    # =========================================================================
    # REALIZED FX GAIN/LOSS
    # =========================================================================
    
    async def calculate_realized_fx_gain_loss(
        self,
        entity_id: uuid.UUID,
        account_id: uuid.UUID,
        fc_amount: Decimal,
        original_rate: Decimal,
        settlement_rate: Decimal,
        settlement_date: date,
        source_document_type: Optional[str] = None,
        source_document_id: Optional[uuid.UUID] = None,
        auto_post: bool = True,
        notes: Optional[str] = None,
    ) -> FXRevaluation:
        """
        Calculate and record realized FX gain/loss.
        
        This is called when:
        - A foreign currency invoice is paid
        - A foreign currency receipt is received
        - A foreign currency bank transfer is made
        
        Args:
            fc_amount: Amount in foreign currency
            original_rate: Exchange rate at original booking
            settlement_rate: Exchange rate at settlement
            auto_post: Whether to auto-create journal entry
        """
        # Get account details
        result = await self.db.execute(
            select(ChartOfAccounts).where(ChartOfAccounts.id == account_id)
        )
        account = result.scalar_one_or_none()
        if not account:
            raise ValueError(f"Account not found: {account_id}")
        
        # Calculate amounts
        original_ngn = (fc_amount * original_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        settled_ngn = (fc_amount * settlement_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        fx_gain_loss = settled_ngn - original_ngn
        
        # Determine FX account type
        fx_account_type = self._determine_fx_account_type(account)
        
        # Create revaluation record
        revaluation = FXRevaluation(
            entity_id=entity_id,
            revaluation_date=settlement_date,
            revaluation_type=FXRevaluationType.REALIZED,
            account_id=account_id,
            fx_account_type=fx_account_type,
            foreign_currency=account.currency,
            functional_currency="NGN",
            original_fc_amount=fc_amount,
            original_exchange_rate=original_rate,
            original_ngn_amount=original_ngn,
            revaluation_rate=settlement_rate,
            revalued_ngn_amount=settled_ngn,
            fx_gain_loss=fx_gain_loss,
            is_gain=fx_gain_loss >= 0,
            source_document_type=source_document_type,
            source_document_id=source_document_id,
            notes=notes,
        )
        self.db.add(revaluation)
        
        # Auto-post journal entry if requested
        if auto_post and fx_gain_loss != 0:
            journal_entry = await self._create_fx_journal_entry(
                entity_id=entity_id,
                account_id=account_id,
                fx_gain_loss=fx_gain_loss,
                entry_date=settlement_date,
                entry_type=JournalEntryType.FX_REALIZED_GAIN_LOSS,
                is_realized=True,
                reference=f"FX Gain/Loss - {account.account_code}",
                notes=notes,
            )
            revaluation.journal_entry_id = journal_entry.id
        
        await self.db.commit()
        await self.db.refresh(revaluation)
        return revaluation
    
    # =========================================================================
    # UNREALIZED FX GAIN/LOSS (PERIOD-END REVALUATION)
    # =========================================================================
    
    async def run_period_end_revaluation(
        self,
        entity_id: uuid.UUID,
        period_id: uuid.UUID,
        revaluation_date: date,
        auto_post: bool = True,
    ) -> Dict[str, Any]:
        """
        Run period-end FX revaluation for all foreign currency accounts.
        
        This creates unrealized FX gain/loss entries for:
        - Foreign currency bank accounts
        - Foreign currency AR balances
        - Foreign currency AP balances
        
        IAS 21 compliant - revalues monetary items at closing rate.
        """
        results = {
            "entity_id": str(entity_id),
            "period_id": str(period_id),
            "revaluation_date": str(revaluation_date),
            "accounts_revalued": [],
            "total_unrealized_gain": Decimal("0.00"),
            "total_unrealized_loss": Decimal("0.00"),
            "net_fx_impact": Decimal("0.00"),
            "journal_entries_created": [],
            "errors": [],
        }
        
        # Get fiscal period
        period_result = await self.db.execute(
            select(FiscalPeriod).where(FiscalPeriod.id == period_id)
        )
        fiscal_period = period_result.scalar_one_or_none()
        if not fiscal_period:
            raise ValueError(f"Fiscal period not found: {period_id}")
        
        # Get all FX accounts
        fx_accounts = await self.get_fx_accounts(entity_id)
        
        for account in fx_accounts:
            try:
                if account.current_balance == 0:
                    continue
                
                # Get current exchange rate
                current_rate = await self.get_exchange_rate(
                    account.currency, "NGN", revaluation_date
                )
                if not current_rate:
                    results["errors"].append(
                        f"No rate for {account.currency}/NGN on {revaluation_date}"
                    )
                    continue
                
                # Get last revaluation rate or original rate
                last_rate = await self._get_last_revaluation_rate(
                    account.id, revaluation_date
                )
                if last_rate is None:
                    # Use a default rate of 1 if no history
                    last_rate = Decimal("1.000000")
                
                # Calculate unrealized gain/loss
                fc_balance = account.current_balance
                old_ngn = (fc_balance * last_rate).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                new_ngn = (fc_balance * current_rate).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                fx_gain_loss = new_ngn - old_ngn
                
                if fx_gain_loss == 0:
                    continue
                
                # Determine FX account type
                fx_account_type = self._determine_fx_account_type(account)
                
                # Create revaluation record
                revaluation = FXRevaluation(
                    entity_id=entity_id,
                    revaluation_date=revaluation_date,
                    revaluation_type=FXRevaluationType.UNREALIZED,
                    account_id=account.id,
                    fx_account_type=fx_account_type,
                    foreign_currency=account.currency,
                    functional_currency="NGN",
                    original_fc_amount=fc_balance,
                    original_exchange_rate=last_rate,
                    original_ngn_amount=old_ngn,
                    revaluation_rate=current_rate,
                    revalued_ngn_amount=new_ngn,
                    fx_gain_loss=fx_gain_loss,
                    is_gain=fx_gain_loss >= 0,
                    fiscal_period_id=period_id,
                    notes=f"Period-end revaluation for {fiscal_period.name}",
                )
                self.db.add(revaluation)
                
                # Track totals
                if fx_gain_loss > 0:
                    results["total_unrealized_gain"] += fx_gain_loss
                else:
                    results["total_unrealized_loss"] += abs(fx_gain_loss)
                
                results["accounts_revalued"].append({
                    "account_code": account.account_code,
                    "account_name": account.account_name,
                    "currency": account.currency,
                    "fc_balance": float(fc_balance),
                    "previous_rate": float(last_rate),
                    "current_rate": float(current_rate),
                    "previous_ngn": float(old_ngn),
                    "current_ngn": float(new_ngn),
                    "fx_gain_loss": float(fx_gain_loss),
                    "is_gain": fx_gain_loss > 0,
                })
                
                # Create journal entry if auto_post
                if auto_post:
                    journal_entry = await self._create_fx_journal_entry(
                        entity_id=entity_id,
                        account_id=account.id,
                        fx_gain_loss=fx_gain_loss,
                        entry_date=revaluation_date,
                        entry_type=JournalEntryType.FX_UNREALIZED_GAIN_LOSS,
                        is_realized=False,
                        reference=f"Unrealized FX - {account.account_code}",
                        period_id=period_id,
                    )
                    revaluation.journal_entry_id = journal_entry.id
                    results["journal_entries_created"].append(str(journal_entry.id))
                
            except Exception as e:
                results["errors"].append(
                    f"Error processing {account.account_code}: {str(e)}"
                )
        
        results["net_fx_impact"] = (
            results["total_unrealized_gain"] - results["total_unrealized_loss"]
        )
        results["total_unrealized_gain"] = float(results["total_unrealized_gain"])
        results["total_unrealized_loss"] = float(results["total_unrealized_loss"])
        results["net_fx_impact"] = float(results["net_fx_impact"])
        
        await self.db.commit()
        return results
    
    async def revalue_open_invoices(
        self,
        entity_id: uuid.UUID,
        revaluation_date: date,
        period_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """
        Revalue open foreign currency invoices at period-end rate.
        
        IAS 21 compliance:
        - Monetary items (receivables) must be revalued at closing rate
        - Any difference is unrealized FX gain/loss
        
        Returns:
            Summary of revaluation with list of revalued invoices
        """
        from app.models.invoice import Invoice, InvoiceStatus
        
        results = {
            "entity_id": str(entity_id),
            "revaluation_date": str(revaluation_date),
            "invoices_revalued": [],
            "total_unrealized_gain": Decimal("0.00"),
            "total_unrealized_loss": Decimal("0.00"),
            "net_fx_impact": Decimal("0.00"),
            "errors": [],
        }
        
        # Get open foreign currency invoices (unpaid or partially paid, not NGN)
        query = select(Invoice).where(and_(
            Invoice.entity_id == entity_id,
            Invoice.status.in_([
                InvoiceStatus.PENDING,
                InvoiceStatus.PARTIALLY_PAID,
                InvoiceStatus.OVERDUE,
            ]),
            Invoice.currency != "NGN",
            Invoice.currency.isnot(None),
        ))
        
        result = await self.db.execute(query)
        invoices = result.scalars().all()
        
        for invoice in invoices:
            try:
                # Skip if no balance due
                balance_due = invoice.total_amount - invoice.amount_paid
                if balance_due <= 0:
                    continue
                
                # Get current exchange rate
                current_rate = await self.get_exchange_rate(
                    invoice.currency, "NGN", revaluation_date
                )
                if not current_rate:
                    results["errors"].append(
                        f"No rate for {invoice.currency}/NGN on {revaluation_date} for invoice {invoice.invoice_number}"
                    )
                    continue
                
                # Get previous rate (last revaluation or booking rate)
                previous_rate = Decimal(str(
                    invoice.last_revaluation_rate or invoice.exchange_rate or "1.0"
                ))
                
                # Calculate unrealized FX gain/loss on outstanding balance
                balance_decimal = Decimal(str(balance_due))
                old_ngn = (balance_decimal * previous_rate).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                new_ngn = (balance_decimal * current_rate).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                fx_gain_loss = new_ngn - old_ngn
                
                if fx_gain_loss == 0:
                    continue
                
                # Update invoice with unrealized FX
                current_unrealized = Decimal(str(invoice.unrealized_fx_gain_loss or "0.00"))
                invoice.unrealized_fx_gain_loss = current_unrealized + fx_gain_loss
                invoice.last_revaluation_date = revaluation_date
                invoice.last_revaluation_rate = float(current_rate)
                
                # Track totals
                if fx_gain_loss > 0:
                    results["total_unrealized_gain"] += fx_gain_loss
                else:
                    results["total_unrealized_loss"] += abs(fx_gain_loss)
                
                results["invoices_revalued"].append({
                    "invoice_number": invoice.invoice_number,
                    "customer_id": str(invoice.customer_id) if invoice.customer_id else None,
                    "currency": invoice.currency,
                    "total_amount": float(invoice.total_amount),
                    "balance_due": float(balance_due),
                    "previous_rate": float(previous_rate),
                    "current_rate": float(current_rate),
                    "previous_ngn": float(old_ngn),
                    "current_ngn": float(new_ngn),
                    "fx_gain_loss": float(fx_gain_loss),
                    "is_gain": fx_gain_loss > 0,
                })
                
            except Exception as e:
                results["errors"].append(
                    f"Error processing invoice {invoice.invoice_number}: {str(e)}"
                )
        
        results["net_fx_impact"] = (
            results["total_unrealized_gain"] - results["total_unrealized_loss"]
        )
        results["total_unrealized_gain"] = float(results["total_unrealized_gain"])
        results["total_unrealized_loss"] = float(results["total_unrealized_loss"])
        results["net_fx_impact"] = float(results["net_fx_impact"])
        
        await self.db.commit()
        return results
    
    async def run_full_period_end_fx_close(
        self,
        entity_id: uuid.UUID,
        period_id: uuid.UUID,
        revaluation_date: date,
        auto_post_journal: bool = True,
    ) -> Dict[str, Any]:
        """
        Run complete period-end FX processing.
        
        This is the main entry point for month-end FX processing that:
        1. Revalues foreign currency GL accounts (bank, AR, AP)
        2. Revalues open foreign currency invoices
        3. Creates unrealized FX gain/loss journal entries
        
        IAS 21 Compliance:
        - All monetary items revalued at closing rate
        - FX differences recognized in profit or loss
        """
        results = {
            "entity_id": str(entity_id),
            "period_id": str(period_id),
            "revaluation_date": str(revaluation_date),
            "gl_revaluation": None,
            "invoice_revaluation": None,
            "combined_summary": {
                "total_unrealized_gain": Decimal("0.00"),
                "total_unrealized_loss": Decimal("0.00"),
                "net_fx_impact": Decimal("0.00"),
            },
            "journal_entry_id": None,
            "success": True,
            "errors": [],
        }
        
        try:
            # 1. Revalue GL accounts
            gl_result = await self.run_period_end_revaluation(
                entity_id=entity_id,
                period_id=period_id,
                revaluation_date=revaluation_date,
                auto_post=False,  # We'll create one combined journal
            )
            results["gl_revaluation"] = gl_result
            
            results["combined_summary"]["total_unrealized_gain"] += Decimal(str(
                gl_result.get("total_unrealized_gain", 0)
            ))
            results["combined_summary"]["total_unrealized_loss"] += Decimal(str(
                gl_result.get("total_unrealized_loss", 0)
            ))
            results["errors"].extend(gl_result.get("errors", []))
            
            # 2. Revalue open invoices
            invoice_result = await self.revalue_open_invoices(
                entity_id=entity_id,
                revaluation_date=revaluation_date,
                period_id=period_id,
            )
            results["invoice_revaluation"] = invoice_result
            
            results["combined_summary"]["total_unrealized_gain"] += Decimal(str(
                invoice_result.get("total_unrealized_gain", 0)
            ))
            results["combined_summary"]["total_unrealized_loss"] += Decimal(str(
                invoice_result.get("total_unrealized_loss", 0)
            ))
            results["errors"].extend(invoice_result.get("errors", []))
            
            # Calculate net impact
            results["combined_summary"]["net_fx_impact"] = (
                results["combined_summary"]["total_unrealized_gain"] - 
                results["combined_summary"]["total_unrealized_loss"]
            )
            
            # 3. Create combined journal entry if auto_post and there's a net impact
            net_impact = results["combined_summary"]["net_fx_impact"]
            if auto_post_journal and net_impact != 0:
                journal_entry = await self._create_combined_fx_journal(
                    entity_id=entity_id,
                    entry_date=revaluation_date,
                    total_gain=results["combined_summary"]["total_unrealized_gain"],
                    total_loss=results["combined_summary"]["total_unrealized_loss"],
                    period_id=period_id,
                )
                results["journal_entry_id"] = str(journal_entry.id)
            
            # Convert Decimals to float for JSON serialization
            results["combined_summary"]["total_unrealized_gain"] = float(
                results["combined_summary"]["total_unrealized_gain"]
            )
            results["combined_summary"]["total_unrealized_loss"] = float(
                results["combined_summary"]["total_unrealized_loss"]
            )
            results["combined_summary"]["net_fx_impact"] = float(
                results["combined_summary"]["net_fx_impact"]
            )
            
            await self.db.commit()
            
        except Exception as e:
            results["success"] = False
            results["errors"].append(f"Critical error: {str(e)}")
            await self.db.rollback()
        
        return results
    
    async def _create_combined_fx_journal(
        self,
        entity_id: uuid.UUID,
        entry_date: date,
        total_gain: Decimal,
        total_loss: Decimal,
        period_id: uuid.UUID,
    ) -> JournalEntry:
        """Create a combined FX gain/loss journal entry."""
        # Get or create FX accounts
        gain_account = await self._get_or_create_fx_account(
            entity_id, self.UNREALIZED_FX_GAIN_ACCOUNT_CODE, is_gain=True, is_realized=False
        )
        loss_account = await self._get_or_create_fx_account(
            entity_id, self.UNREALIZED_FX_LOSS_ACCOUNT_CODE, is_gain=False, is_realized=False
        )
        
        # Get AR account for contra entry
        ar_result = await self.db.execute(
            select(ChartOfAccounts).where(and_(
                ChartOfAccounts.entity_id == entity_id,
                ChartOfAccounts.account_code == "1130",  # Accounts Receivable
            ))
        )
        ar_account = ar_result.scalar_one_or_none()
        
        # Build journal lines
        lines = []
        
        # If net gain: Dr AR, Cr FX Gain
        # If net loss: Dr FX Loss, Cr AR
        net_impact = total_gain - total_loss
        
        if net_impact > 0:
            # Net gain
            lines.append(JournalEntryLine(
                account_id=ar_account.id if ar_account else gain_account.id,
                description="Unrealized FX Gain - Period End Revaluation",
                debit_amount=net_impact,
                credit_amount=Decimal("0.00"),
            ))
            lines.append(JournalEntryLine(
                account_id=gain_account.id,
                description="Unrealized FX Gain - Period End Revaluation",
                debit_amount=Decimal("0.00"),
                credit_amount=net_impact,
            ))
        elif net_impact < 0:
            # Net loss
            lines.append(JournalEntryLine(
                account_id=loss_account.id,
                description="Unrealized FX Loss - Period End Revaluation",
                debit_amount=abs(net_impact),
                credit_amount=Decimal("0.00"),
            ))
            lines.append(JournalEntryLine(
                account_id=ar_account.id if ar_account else loss_account.id,
                description="Unrealized FX Loss - Period End Revaluation",
                debit_amount=Decimal("0.00"),
                credit_amount=abs(net_impact),
            ))
        
        # Create journal entry
        entry = JournalEntry(
            entity_id=entity_id,
            entry_date=entry_date,
            reference=f"FX-REVAL-{entry_date.strftime('%Y%m')}",
            description=f"Period-End FX Revaluation - {entry_date.strftime('%B %Y')}",
            entry_type=JournalEntryType.FX_UNREALIZED_GAIN_LOSS,
            status=JournalEntryStatus.POSTED,
            fiscal_period_id=period_id,
            is_system_entry=True,
            total_debit=abs(net_impact),
            total_credit=abs(net_impact),
        )
        self.db.add(entry)
        await self.db.flush()
        
        # Add lines to entry
        for line in lines:
            line.journal_entry_id = entry.id
            self.db.add(line)
        
        return entry

    # =========================================================================
    # FX REPORTS
    # =========================================================================
    
    async def get_fx_gain_loss_report(
        self,
        entity_id: uuid.UUID,
        start_date: date,
        end_date: date,
        currency: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate FX gain/loss report for a period."""
        query = select(FXRevaluation).where(and_(
            FXRevaluation.entity_id == entity_id,
            FXRevaluation.revaluation_date >= start_date,
            FXRevaluation.revaluation_date <= end_date,
        ))
        
        if currency:
            query = query.where(FXRevaluation.foreign_currency == currency)
        
        query = query.order_by(FXRevaluation.revaluation_date)
        
        result = await self.db.execute(query)
        revaluations = result.scalars().all()
        
        # Summarize by type and currency
        summary = {
            "period": {"start": str(start_date), "end": str(end_date)},
            "realized": {
                "total_gain": Decimal("0.00"),
                "total_loss": Decimal("0.00"),
                "net": Decimal("0.00"),
                "by_currency": {},
            },
            "unrealized": {
                "total_gain": Decimal("0.00"),
                "total_loss": Decimal("0.00"),
                "net": Decimal("0.00"),
                "by_currency": {},
            },
            "total_fx_impact": Decimal("0.00"),
            "details": [],
        }
        
        for reval in revaluations:
            detail = {
                "date": str(reval.revaluation_date),
                "type": reval.revaluation_type.value,
                "currency": reval.foreign_currency,
                "fc_amount": float(reval.original_fc_amount),
                "original_rate": float(reval.original_exchange_rate),
                "revaluation_rate": float(reval.revaluation_rate),
                "fx_gain_loss": float(reval.fx_gain_loss),
                "is_gain": reval.is_gain,
            }
            summary["details"].append(detail)
            
            # Aggregate by type
            type_key = "realized" if reval.revaluation_type == FXRevaluationType.REALIZED else "unrealized"
            
            if reval.is_gain:
                summary[type_key]["total_gain"] += reval.fx_gain_loss
            else:
                summary[type_key]["total_loss"] += abs(reval.fx_gain_loss)
            
            # Aggregate by currency
            curr = reval.foreign_currency
            if curr not in summary[type_key]["by_currency"]:
                summary[type_key]["by_currency"][curr] = {
                    "gain": Decimal("0.00"),
                    "loss": Decimal("0.00"),
                }
            
            if reval.is_gain:
                summary[type_key]["by_currency"][curr]["gain"] += reval.fx_gain_loss
            else:
                summary[type_key]["by_currency"][curr]["loss"] += abs(reval.fx_gain_loss)
        
        # Calculate nets
        summary["realized"]["net"] = (
            summary["realized"]["total_gain"] - summary["realized"]["total_loss"]
        )
        summary["unrealized"]["net"] = (
            summary["unrealized"]["total_gain"] - summary["unrealized"]["total_loss"]
        )
        summary["total_fx_impact"] = summary["realized"]["net"] + summary["unrealized"]["net"]
        
        # Convert to float for JSON serialization
        for key in ["total_gain", "total_loss", "net"]:
            summary["realized"][key] = float(summary["realized"][key])
            summary["unrealized"][key] = float(summary["unrealized"][key])
        summary["total_fx_impact"] = float(summary["total_fx_impact"])
        
        for curr_data in summary["realized"]["by_currency"].values():
            curr_data["gain"] = float(curr_data["gain"])
            curr_data["loss"] = float(curr_data["loss"])
        for curr_data in summary["unrealized"]["by_currency"].values():
            curr_data["gain"] = float(curr_data["gain"])
            curr_data["loss"] = float(curr_data["loss"])
        
        return summary
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _determine_fx_account_type(self, account: ChartOfAccounts) -> FXAccountType:
        """Determine the FX account type from chart of accounts."""
        if account.account_sub_type == AccountSubType.BANK:
            return FXAccountType.BANK
        elif account.account_sub_type == AccountSubType.ACCOUNTS_RECEIVABLE:
            return FXAccountType.RECEIVABLE
        elif account.account_sub_type == AccountSubType.ACCOUNTS_PAYABLE:
            return FXAccountType.PAYABLE
        elif account.account_sub_type == AccountSubType.LOAN:
            return FXAccountType.LOAN
        else:
            return FXAccountType.BANK  # Default
    
    async def _get_last_revaluation_rate(
        self,
        account_id: uuid.UUID,
        before_date: date,
    ) -> Optional[Decimal]:
        """Get the last revaluation rate for an account."""
        result = await self.db.execute(
            select(FXRevaluation.revaluation_rate)
            .where(and_(
                FXRevaluation.account_id == account_id,
                FXRevaluation.revaluation_date < before_date,
            ))
            .order_by(FXRevaluation.revaluation_date.desc())
            .limit(1)
        )
        rate = result.scalar_one_or_none()
        return rate
    
    async def _create_fx_journal_entry(
        self,
        entity_id: uuid.UUID,
        account_id: uuid.UUID,
        fx_gain_loss: Decimal,
        entry_date: date,
        entry_type: JournalEntryType,
        is_realized: bool,
        reference: str,
        period_id: Optional[uuid.UUID] = None,
        notes: Optional[str] = None,
    ) -> JournalEntry:
        """Create journal entry for FX gain/loss."""
        # Get the source account
        result = await self.db.execute(
            select(ChartOfAccounts).where(ChartOfAccounts.id == account_id)
        )
        source_account = result.scalar_one()
        
        # Determine FX gain/loss account codes
        if is_realized:
            gain_code = self.FX_GAIN_ACCOUNT_CODE
            loss_code = self.FX_LOSS_ACCOUNT_CODE
        else:
            gain_code = self.UNREALIZED_FX_GAIN_ACCOUNT_CODE
            loss_code = self.UNREALIZED_FX_LOSS_ACCOUNT_CODE
        
        # Get or create FX gain/loss accounts
        fx_pl_account = await self._get_or_create_fx_account(
            entity_id,
            gain_code if fx_gain_loss > 0 else loss_code,
            is_gain=fx_gain_loss > 0,
            is_realized=is_realized,
        )
        
        # Determine journal number
        import random
        entry_number = f"FX-{entry_date.strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
        
        # Create journal entry
        abs_amount = abs(fx_gain_loss)
        
        # If gain: DR source account (increase), CR FX Gain (income)
        # If loss: DR FX Loss (expense), CR source account (decrease)
        
        journal_entry = JournalEntry(
            entity_id=entity_id,
            fiscal_period_id=period_id,
            entry_number=entry_number,
            entry_date=entry_date,
            entry_type=entry_type,
            source_reference=reference,
            description=f"{'Realized' if is_realized else 'Unrealized'} FX {'Gain' if fx_gain_loss > 0 else 'Loss'} - {source_account.account_name}",
            memo=notes,
            total_debit=abs_amount,
            total_credit=abs_amount,
            currency="NGN",
            exchange_rate=Decimal("1.000000"),
            status=JournalEntryStatus.POSTED,
            posted_at=datetime.utcnow(),
        )
        self.db.add(journal_entry)
        await self.db.flush()
        
        # Create journal entry lines
        if fx_gain_loss > 0:
            # FX Gain
            lines = [
                JournalEntryLine(
                    journal_entry_id=journal_entry.id,
                    line_number=1,
                    account_id=account_id,
                    description=f"FX Gain adjustment",
                    debit_amount=abs_amount,
                    credit_amount=Decimal("0.00"),
                ),
                JournalEntryLine(
                    journal_entry_id=journal_entry.id,
                    line_number=2,
                    account_id=fx_pl_account.id,
                    description=f"FX Gain - {source_account.currency}",
                    debit_amount=Decimal("0.00"),
                    credit_amount=abs_amount,
                ),
            ]
        else:
            # FX Loss
            lines = [
                JournalEntryLine(
                    journal_entry_id=journal_entry.id,
                    line_number=1,
                    account_id=fx_pl_account.id,
                    description=f"FX Loss - {source_account.currency}",
                    debit_amount=abs_amount,
                    credit_amount=Decimal("0.00"),
                ),
                JournalEntryLine(
                    journal_entry_id=journal_entry.id,
                    line_number=2,
                    account_id=account_id,
                    description=f"FX Loss adjustment",
                    debit_amount=Decimal("0.00"),
                    credit_amount=abs_amount,
                ),
            ]
        
        for line in lines:
            self.db.add(line)
        
        return journal_entry
    
    async def _get_or_create_fx_account(
        self,
        entity_id: uuid.UUID,
        account_code: str,
        is_gain: bool,
        is_realized: bool,
    ) -> ChartOfAccounts:
        """Get or create FX gain/loss account."""
        result = await self.db.execute(
            select(ChartOfAccounts).where(and_(
                ChartOfAccounts.entity_id == entity_id,
                ChartOfAccounts.account_code == account_code,
            ))
        )
        account = result.scalar_one_or_none()
        
        if account:
            return account
        
        # Create the account
        if is_gain:
            if is_realized:
                name = "Realized Foreign Exchange Gain"
                account_type = AccountType.REVENUE
                sub_type = AccountSubType.OTHER_INCOME
            else:
                name = "Unrealized Foreign Exchange Gain"
                account_type = AccountType.REVENUE
                sub_type = AccountSubType.OTHER_INCOME
        else:
            if is_realized:
                name = "Realized Foreign Exchange Loss"
                account_type = AccountType.EXPENSE
                sub_type = AccountSubType.OTHER_EXPENSE
            else:
                name = "Unrealized Foreign Exchange Loss"
                account_type = AccountType.EXPENSE
                sub_type = AccountSubType.OTHER_EXPENSE
        
        new_account = ChartOfAccounts(
            entity_id=entity_id,
            account_code=account_code,
            account_name=name,
            description=f"System account for {'realized' if is_realized else 'unrealized'} FX {'gains' if is_gain else 'losses'}",
            account_type=account_type,
            account_sub_type=sub_type,
            normal_balance=NormalBalance.CREDIT if is_gain else NormalBalance.DEBIT,
            level=1,
            is_header=False,
            is_active=True,
            is_system_account=True,
        )
        self.db.add(new_account)
        await self.db.flush()
        
        return new_account
