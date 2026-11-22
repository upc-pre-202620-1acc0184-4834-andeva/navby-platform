from typing import Protocol

from src.modules.quotes.domain.model.value_objects.exchange_rates import ExchangeRates
from src.shared.application.result import Result


class ExchangeRateProvider(Protocol):
    async def fetch_usd_rates(self) -> Result[ExchangeRates]: ...
