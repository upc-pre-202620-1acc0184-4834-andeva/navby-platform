from datetime import UTC, datetime
from decimal import Decimal

from src.modules.quotes.application.acl.ports.exchange_rate_cache import (
    ExchangeRateCache,
)
from src.modules.quotes.application.acl.ports.exchange_rate_provider import (
    ExchangeRateProvider,
)
from src.modules.quotes.domain.model.value_objects.exchange_rates import ExchangeRates

RATES_TTL_SECONDS = 6 * 3600
# El respaldo se guarda poco tiempo para reintentar pronto con el proveedor.
FALLBACK_TTL_SECONDS = 300


class GetExchangeRatesHandler:
    def __init__(
        self,
        provider: ExchangeRateProvider,
        cache: ExchangeRateCache,
        fallback_pen_per_usd: Decimal,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._fallback_pen_per_usd = fallback_pen_per_usd

    async def handle(self) -> ExchangeRates:
        cached = await self._cache.get()
        if cached is not None:
            return cached

        fetched = await self._provider.fetch_usd_rates()
        if fetched.is_success:
            await self._cache.put(fetched.value, RATES_TTL_SECONDS)
            return fetched.value

        fallback = ExchangeRates(
            rates={"USD": Decimal("1"), "PEN": self._fallback_pen_per_usd},
            as_of=datetime.now(UTC),
            source="fallback",
        )
        await self._cache.put(fallback, FALLBACK_TTL_SECONDS)
        return fallback
