import logging
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from src.modules.quotes.application.acl.ports.exchange_rate_provider import (
    ExchangeRateProvider,
)
from src.modules.quotes.domain.model.value_objects.exchange_rates import (
    DISPLAY_CURRENCIES,
    ExchangeRates,
)
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result

logger = logging.getLogger(__name__)


class OpenErApiExchangeRateProvider(ExchangeRateProvider):
    """Tipos de cambio diarios de open.er-api.com (gratis, sin clave; exige atribución)."""

    URL = "https://open.er-api.com/v6/latest/USD"

    def __init__(self, timeout_seconds: float = 5.0) -> None:
        self._timeout = timeout_seconds

    async def fetch_usd_rates(self) -> Result[ExchangeRates]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(self.URL)
            resp.raise_for_status()
            data = resp.json()
            rates = {code: Decimal(str(data["rates"][code])) for code in DISPLAY_CURRENCIES}
            if data["result"] != "success" or any(rate <= 0 for rate in rates.values()):
                raise ValueError("unexpected exchange rate payload")
            as_of = datetime.fromtimestamp(int(data["time_last_update_unix"]), UTC)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, ArithmeticError) as exc:
            logger.warning("Exchange rate provider failed: %s", type(exc).__name__)
            return Result.failure(
                ApplicationError(
                    code="PROVIDER_UNAVAILABLE",
                    message="No se pudo obtener el tipo de cambio.",
                )
            )
        return Result.success(ExchangeRates(rates=rates, as_of=as_of, source="provider"))
