"""
Exchange Rate Service — clear service-layer boundary for external currency data.

This module is the single integration point for the open.er-api.com exchange
rate API.  Nothing outside this module makes raw HTTP calls or parses the
third-party JSON directly — routers and the rest of the app interact only
with the high-level methods defined below.

Design characteristics:
  - Async HTTP via httpx (non-blocking, plays well with FastAPI/asyncio).
  - In-memory TTL cache so we never hammer the external API on every request.
  - Transparent fallback: if the network is unavailable we return whatever
    the cache holds (even if stale), or raise a clear 503 if nothing is
    cached yet.
  - Stateless constructor: one instance is created at application startup
    (via dependency injection) and reused across all requests.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class _RateCache:
    """Simple TTL cache for a single base-currency rates snapshot."""
    base: str = ""
    rates: dict[str, Decimal] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=lambda: datetime.min.replace(tzinfo=timezone.utc))
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def is_fresh(self, ttl_seconds: int) -> bool:
        age = (datetime.now(timezone.utc) - self.fetched_at).total_seconds()
        return bool(self.rates) and age < ttl_seconds


@dataclass
class CurrencyConversionResult:
    amount: Decimal
    from_currency: str
    to_currency: str
    converted_amount: Decimal
    exchange_rate: Decimal
    timestamp: datetime


class ExchangeRateService:
    """
    Service facade for external exchange rate data.

    Public API:
      get_rates(base)            → dict[str, Decimal]   (all rates vs. base)
      get_rate(from_, to_)       → Decimal              (single pair rate)
      convert(amount, from_, to) → CurrencyConversionResult
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._api_url: str = settings.exchange_rate_api_url
        self._ttl: int = settings.exchange_rate_cache_ttl_seconds
        # One cache entry per base currency (lazy-populated on first use)
        self._caches: dict[str, _RateCache] = {}

    # ------------------------------------------------------------------
    # Public service methods
    # ------------------------------------------------------------------

    async def get_rates(self, base: str = "USD") -> tuple[dict[str, Decimal], datetime]:
        """Return all exchange rates for *base* and the data timestamp."""
        base = base.upper()
        cache = self._get_or_create_cache(base)
        await self._ensure_fresh(cache, base)
        return dict(cache.rates), cache.fetched_at

    async def get_rate(self, from_currency: str, to_currency: str) -> Decimal:
        """
        Return how many *to_currency* units equal one *from_currency* unit.
        Uses cross-rate arithmetic when both currencies share a common base.
        """
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        if from_currency == to_currency:
            return Decimal("1")

        # Fetch USD-based rates (cheapest — one API call covers all pairs)
        rates, _ = await self.get_rates("USD")

        if from_currency not in rates:
            raise ValueError(f"Unknown currency code: {from_currency!r}")
        if to_currency not in rates:
            raise ValueError(f"Unknown currency code: {to_currency!r}")

        # Cross-rate: rate(from→to) = rate(USD→to) / rate(USD→from)
        return rates[to_currency] / rates[from_currency]

    async def convert(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
    ) -> CurrencyConversionResult:
        """Convert *amount* from *from_currency* to *to_currency*."""
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        rate = await self.get_rate(from_currency, to_currency)
        converted = (amount * rate).quantize(Decimal("0.01"))
        _, timestamp = await self.get_rates("USD")

        return CurrencyConversionResult(
            amount=amount,
            from_currency=from_currency,
            to_currency=to_currency,
            converted_amount=converted,
            exchange_rate=rate.quantize(Decimal("0.000001")),
            timestamp=timestamp,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_cache(self, base: str) -> _RateCache:
        if base not in self._caches:
            self._caches[base] = _RateCache(base=base)
        return self._caches[base]

    async def _ensure_fresh(self, cache: _RateCache, base: str) -> None:
        """Populate or refresh *cache* if it is stale, using a lock to
        prevent thundering-herd on the external API."""
        if cache.is_fresh(self._ttl):
            return

        async with cache.lock:
            # Double-checked locking: another coroutine may have populated
            # the cache while we were waiting for the lock.
            if cache.is_fresh(self._ttl):
                return
            await self._fetch_and_populate(cache, base)

    async def _fetch_and_populate(self, cache: _RateCache, base: str) -> None:
        """Hit the external API and update *cache*. Falls back to stale data
        (or raises 503) if the network is unavailable."""
        url = f"{self._api_url}/{base}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

            raw_rates: dict = data.get("rates", {})
            parsed: dict[str, Decimal] = {}
            for code, value in raw_rates.items():
                try:
                    parsed[code.upper()] = Decimal(str(value))
                except InvalidOperation:
                    pass  # silently skip malformed rate entries

            # Always include the base itself at 1.0
            parsed[base.upper()] = Decimal("1")

            cache.rates = parsed
            cache.fetched_at = datetime.now(timezone.utc)
            logger.info("Exchange rates refreshed for base=%s (%d currencies)", base, len(parsed))

        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning(
                "Failed to refresh exchange rates for base=%s: %s. "
                "Serving stale cache if available.",
                base,
                exc,
            )
            if not cache.rates:
                raise RuntimeError(
                    "Exchange rate service is unavailable and no cached data exists. "
                    "Please try again later."
                ) from exc
            # Otherwise silently serve stale data
