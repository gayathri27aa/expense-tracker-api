"""
Currency & Exchange Rate router.

Endpoints:
  GET /currencies/rates    — live exchange rates for a base currency
  GET /currencies/convert  — convert an amount between two currencies

Both endpoints are protected: a valid Bearer token is required.
The actual rate fetching, caching, and cross-rate arithmetic are
completely encapsulated in ExchangeRateService (app/services/exchange_rate.py).
Routers only handle HTTP concerns: input validation, response shaping,
and error mapping.
"""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_current_user, get_exchange_rate_service
from app.models.user import User
from app.schemas.currency import CurrencyConversionResponse, ExchangeRatesResponse
from app.services.exchange_rate import ExchangeRateService

router = APIRouter(prefix="/currencies", tags=["currencies"])


@router.get(
    "/rates",
    response_model=ExchangeRatesResponse,
    summary="Get live exchange rates for a base currency",
)
async def get_exchange_rates(
    base: Annotated[
        str,
        Query(
            min_length=3,
            max_length=3,
            description="3-letter ISO 4217 base currency code (default: USD)",
        ),
    ] = "USD",
    _: User = Depends(get_current_user),
    service: ExchangeRateService = Depends(get_exchange_rate_service),
) -> ExchangeRatesResponse:
    """
    Return all available exchange rates expressed relative to *base*.
    Rates are cached for up to 1 hour to limit external API calls.

    Example: `GET /currencies/rates?base=INR`
    """
    try:
        rates, timestamp = await service.get_rates(base.upper())
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )

    if not rates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No rates found for base currency '{base.upper()}'. "
                   "Verify the currency code is a valid ISO 4217 code.",
        )

    return ExchangeRatesResponse(base=base.upper(), rates=rates, timestamp=timestamp)


@router.get(
    "/convert",
    response_model=CurrencyConversionResponse,
    summary="Convert an amount between two currencies",
)
async def convert_currency(
    amount: Annotated[
        Decimal,
        Query(gt=0, description="Positive amount to convert"),
    ],
    from_currency: Annotated[
        str,
        Query(
            min_length=3,
            max_length=3,
            description="Source currency code (e.g. USD)",
        ),
    ],
    to_currency: Annotated[
        str,
        Query(
            min_length=3,
            max_length=3,
            description="Target currency code (e.g. INR)",
        ),
    ],
    _: User = Depends(get_current_user),
    service: ExchangeRateService = Depends(get_exchange_rate_service),
) -> CurrencyConversionResponse:
    """
    Convert *amount* from *from_currency* to *to_currency* using live rates.

    Example: `GET /currencies/convert?amount=100&from_currency=USD&to_currency=INR`
    """
    try:
        result = await service.convert(amount, from_currency, to_currency)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )

    return CurrencyConversionResponse(
        amount=result.amount,
        from_currency=result.from_currency,
        to_currency=result.to_currency,
        converted_amount=result.converted_amount,
        exchange_rate=result.exchange_rate,
        timestamp=result.timestamp,
    )
