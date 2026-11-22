from typing import Protocol

from src.modules.quotes.domain.model.value_objects.exchange_rates import ExchangeRates


class ExchangeRateCache(Protocol):
    async def get(self) -> ExchangeRates | None: ...

    async def put(self, rates: ExchangeRates, ttl_seconds: int) -> None: ...
