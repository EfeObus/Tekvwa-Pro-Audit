"""
Tekvwa Pro Audit - Foreign Exchange (FX) Router

API endpoints for multi-currency operations including:
- Exchange rate management
- FX gain/loss calculation
- Period-end revaluation
- FX exposure reporting

Nigerian IFRS Compliant - IAS 21 Implementation

SKU Requirement: PROFESSIONAL tier or higher (Feature.MULTI_CURRENCY)
"""

import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_feature, require_entity_access
from app.models.user import User
from app.models.entity import BusinessEntity
from app.models.sku_enums import Feature
from app.schemas.accounting import (
    ExchangeRateCreate, ExchangeRateResponse,
    CurrencyConversionRequest, CurrencyConversionResponse,
    FXExposureReport, FXExposureByCurrency,
    RealizedFXGainLossRequest, FXRevaluationResponse,
    PeriodEndRevaluationRequest, FXRevaluationSummary,
    FXGainLossReport,
)
from app.services.fx_service import FXService

# Feature gate - requires Professional tier or higher
fx_feature_gate = require_feature([Feature.MULTI_CURRENCY])

router = APIRouter(
    prefix="/api/v1/entities/{entity_id}/fx",
    tags=["Foreign Exchange (FX)"],
    dependencies=[Depends(fx_feature_gate)],
)


# ============================================================================
# EXCHANGE RATE MANAGEMENT
# ============================================================================

@router.get("/exchange-rates")
async def get_exchange_rates(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    base_currency: str = Query("NGN", description="Base currency"),
    rate_date: Optional[date] = Query(None, description="Rate date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get all exchange rates to base currency.
    
    Returns exchange rates for all configured currencies.
    If rate_date is not specified, uses today's date.
    """
    service = FXService(db)
    rates = await service.get_all_exchange_rates(base_currency, rate_date)
    return {
        "base_currency": base_currency,
        "rate_date": str(rate_date or date.today()),
        "rates": {k: float(v) for k, v in rates.items()}
    }


@router.get("/exchange-rates/{from_currency}/{to_currency}")
async def get_exchange_rate(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    from_currency: str = Path(..., min_length=3, max_length=3),
    to_currency: str = Path(..., min_length=3, max_length=3),
    rate_date: Optional[date] = Query(None, description="Rate date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get exchange rate for a currency pair.
    
    Returns the most recent rate on or before the specified date.
    """
    service = FXService(db)
    rate = await service.get_exchange_rate(from_currency, to_currency, rate_date)
    
    if rate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No exchange rate found for {from_currency}/{to_currency}"
        )
    
    return {
        "from_currency": from_currency,
        "to_currency": to_currency,
        "rate": float(rate),
        "rate_date": str(rate_date or date.today())
    }


@router.post("/exchange-rates", response_model=ExchangeRateResponse)
async def create_exchange_rate(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    data: ExchangeRateCreate = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create or update an exchange rate.
    
    If a rate already exists for the currency pair and date, it will be updated.
    """
    service = FXService(db)
    rate = await service.update_exchange_rate(
        from_currency=data.from_currency,
        to_currency=data.to_currency,
        rate=data.rate,
        rate_date=data.rate_date,
        source=data.source,
        is_billing_rate=data.is_billing_rate,
    )
    return rate


# ============================================================================
# CURRENCY CONVERSION
# ============================================================================

@router.post("/convert", response_model=CurrencyConversionResponse)
async def convert_currency(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    data: CurrencyConversionRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Convert amount from one currency to another.
    
    Uses the exchange rate for the specified date.
    If exchange_rate is provided in the request, uses that instead.
    """
    service = FXService(db)
    
    try:
        converted_amount, rate_used = await service.convert_amount(
            amount=data.amount,
            from_currency=data.from_currency,
            to_currency=data.to_currency,
            rate_date=data.rate_date,
            exchange_rate=data.exchange_rate,
        )
        
        return CurrencyConversionResponse(
            original_amount=data.amount,
            from_currency=data.from_currency,
            to_currency=data.to_currency,
            converted_amount=converted_amount,
            exchange_rate=rate_used,
            rate_date=data.rate_date or date.today(),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ============================================================================
# FX EXPOSURE
# ============================================================================

@router.get("/exposure")
async def get_fx_exposure(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    as_of_date: Optional[date] = Query(None, description="As of date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get FX exposure summary by currency.
    
    Returns breakdown of:
    - Bank account balances in foreign currency
    - Receivable balances in foreign currency
    - Payable balances in foreign currency
    - Net exposure with NGN equivalent
    """
    service = FXService(db)
    exposures = await service.get_fx_exposure_by_currency(entity_id, as_of_date)
    
    # Calculate total
    total_ngn = sum(
        exp.get("ngn_equivalent", 0) or 0 
        for exp in exposures.values()
    )
    
    return {
        "entity_id": str(entity_id),
        "as_of_date": str(as_of_date or date.today()),
        "functional_currency": "NGN",
        "exposures": list(exposures.values()),
        "total_net_exposure_ngn": total_ngn,
    }


@router.get("/exposure/{currency}")
async def get_fx_exposure_by_currency(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    currency: str = Path(..., min_length=3, max_length=3),
    as_of_date: Optional[date] = Query(None, description="As of date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get FX exposure for a specific currency."""
    service = FXService(db)
    exposures = await service.get_fx_exposure_by_currency(entity_id, as_of_date)
    
    if currency not in exposures:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No FX exposure found for {currency}"
        )
    
    return exposures[currency]


# ============================================================================
# REALIZED FX GAIN/LOSS
# ============================================================================

@router.post("/realized-gain-loss", response_model=FXRevaluationResponse)
async def calculate_realized_fx_gain_loss(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    data: RealizedFXGainLossRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Calculate and record realized FX gain/loss.
    
    Called when:
    - A foreign currency invoice is paid
    - A foreign currency receipt is received
    - A foreign currency bank transfer is settled
    
    If auto_post is True (default), creates a journal entry for the gain/loss.
    """
    service = FXService(db)
    
    try:
        revaluation = await service.calculate_realized_fx_gain_loss(
            entity_id=entity_id,
            account_id=data.account_id,
            fc_amount=data.fc_amount,
            original_rate=data.original_rate,
            settlement_rate=data.settlement_rate,
            settlement_date=data.settlement_date,
            source_document_type=data.source_document_type,
            source_document_id=data.source_document_id,
            auto_post=data.auto_post,
            notes=data.notes,
        )
        return revaluation
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ============================================================================
# PERIOD-END REVALUATION (UNREALIZED FX)
# ============================================================================

@router.post("/period-end-revaluation")
async def run_period_end_revaluation(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    data: PeriodEndRevaluationRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run period-end FX revaluation.
    
    IAS 21 Compliant - Revalues all monetary items denominated in 
    foreign currencies at the closing exchange rate.
    
    Creates unrealized FX gain/loss entries for:
    - Foreign currency bank accounts (domiciliary)
    - Foreign currency AR balances
    - Foreign currency AP balances
    
    If auto_post is True (default), creates journal entries for each revaluation.
    
    NOTE: Run this at the end of each accounting period before closing.
    """
    service = FXService(db)
    
    try:
        results = await service.run_period_end_revaluation(
            entity_id=entity_id,
            period_id=data.period_id,
            revaluation_date=data.revaluation_date,
            auto_post=data.auto_post,
        )
        return results
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ============================================================================
# FX REPORTS
# ============================================================================

@router.get("/reports/gain-loss")
async def get_fx_gain_loss_report(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    start_date: date = Query(..., description="Report start date"),
    end_date: date = Query(..., description="Report end date"),
    currency: Optional[str] = Query(None, description="Filter by currency"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate FX gain/loss report for a period.
    
    Returns:
    - Realized gains and losses (from actual transactions)
    - Unrealized gains and losses (from period-end revaluations)
    - Breakdown by currency
    - Total FX impact on profit/loss
    """
    service = FXService(db)
    report = await service.get_fx_gain_loss_report(
        entity_id=entity_id,
        start_date=start_date,
        end_date=end_date,
        currency=currency,
    )
    return report


@router.get("/reports/fx-accounts")
async def get_fx_accounts(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get all accounts with foreign currency exposure.
    
    Returns list of accounts where currency is not NGN.
    """
    service = FXService(db)
    accounts = await service.get_fx_accounts(entity_id)
    
    return {
        "entity_id": str(entity_id),
        "fx_accounts": [
            {
                "id": str(acc.id),
                "account_code": acc.account_code,
                "account_name": acc.account_name,
                "currency": acc.currency,
                "account_type": acc.account_type.value,
                "account_sub_type": acc.account_sub_type.value if acc.account_sub_type else None,
                "current_balance": float(acc.current_balance),
            }
            for acc in accounts
        ],
        "total_accounts": len(accounts),
    }
