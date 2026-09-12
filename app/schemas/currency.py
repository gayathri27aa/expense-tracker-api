from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class CurrencyConversionResponse(BaseModel):
    amount: Decimal = Field(..., description="Original input amount")
    from_currency: str = Field(..., min_length=3, max_length=3, description="Source currency code")
    to_currency: str = Field(..., min_length=3, max_length=3, description="Target currency code")
    converted_amount: Decimal = Field(..., description="Calculated converted amount")
    exchange_rate: Decimal = Field(..., description="Exchange rate applied (1 from_currency = rate to_currency)")
    timestamp: datetime = Field(..., description="Timestamp of the rate data")


class ExchangeRatesResponse(BaseModel):
    base: str = Field(..., min_length=3, max_length=3, description="Base currency code")
    rates: dict[str, Decimal] = Field(..., description="Exchange rates dictionary keyed by currency code")
    timestamp: datetime = Field(..., description="Timestamp of the rate data")
