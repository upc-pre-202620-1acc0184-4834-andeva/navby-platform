from datetime import UTC, datetime
from decimal import Decimal

import httpx
import respx

from src.modules.quotes.application.queries.get_exchange_rates import (
    FALLBACK_TTL_SECONDS,
    RATES_TTL_SECONDS,
    GetExchangeRatesHandler,
)
from src.modules.quotes.domain.model.value_objects.exchange_rates import ExchangeRates
from src.modules.quotes.infrastructure.adapters.open_er_api_exchange_rate_provider import (
    OpenErApiExchangeRateProvider,
)
from src.modules.quotes.infrastructure.cache.redis_exchange_rate_cache import (
    RedisExchangeRateCache,
)
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result

PROVIDER_URL = OpenErApiExchangeRateProvider.URL
NOW = datetime(2026, 11, 22, tzinfo=UTC)


class FakeProvider:
    def __init__(self, result: Result[ExchangeRates]) -> None:
        self.result = result
        self.calls = 0

    async def fetch_usd_rates(self) -> Result[ExchangeRates]:
        self.calls += 1
        return self.result


class FakeCache:
    def __init__(self, stored: ExchangeRates | None = None) -> None:
        self.stored = stored
        self.puts: list[tuple[ExchangeRates, int]] = []

    async def get(self) -> ExchangeRates | None:
        return self.stored

    async def put(self, rates: ExchangeRates, ttl_seconds: int) -> None:
        self.stored = rates
        self.puts.append((rates, ttl_seconds))


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, tuple[str, int]] = {}

    async def get(self, key: str) -> str | None:
        item = self.data.get(key)
        return item[0] if item else None

    async def set(self, key: str, value: str, ex: int) -> None:
        self.data[key] = (value, ex)


def _rates(pen: str = "3.44", source: str = "provider") -> ExchangeRates:
    return ExchangeRates(rates={"USD": Decimal("1"), "PEN": Decimal(pen)}, as_of=NOW, source=source)


def _handler(provider: FakeProvider, cache: FakeCache) -> GetExchangeRatesHandler:
    return GetExchangeRatesHandler(provider, cache, fallback_pen_per_usd=Decimal("3.5"))


async def test_cached_rates_skip_the_provider() -> None:
    provider = FakeProvider(Result.success(_rates("9.99")))
    cache = FakeCache(_rates("3.44"))

    rates = await _handler(provider, cache).handle()

    assert rates.rates["PEN"] == Decimal("3.44")
    assert provider.calls == 0


async def test_cache_miss_fetches_and_stores_for_six_hours() -> None:
    provider = FakeProvider(Result.success(_rates("3.41")))
    cache = FakeCache()

    rates = await _handler(provider, cache).handle()

    assert rates.source == "provider"
    assert cache.puts == [(rates, RATES_TTL_SECONDS)]


async def test_provider_failure_returns_short_lived_fallback() -> None:
    failure = Result[ExchangeRates].failure(
        ApplicationError(code="PROVIDER_UNAVAILABLE", message="down")
    )
    provider = FakeProvider(failure)
    cache = FakeCache()

    rates = await _handler(provider, cache).handle()

    assert rates.source == "fallback"
    assert rates.rates == {"USD": Decimal("1"), "PEN": Decimal("3.5")}
    assert cache.puts == [(rates, FALLBACK_TTL_SECONDS)]


@respx.mock
async def test_adapter_reads_usd_and_pen_rates() -> None:
    respx.get(PROVIDER_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": "success",
                "time_last_update_unix": 1795392152,
                "rates": {"USD": 1, "PEN": 3.441274, "EUR": 0.86},
            },
        )
    )

    result = await OpenErApiExchangeRateProvider().fetch_usd_rates()

    assert result.is_success
    assert result.value.rates == {"USD": Decimal("1"), "PEN": Decimal("3.441274")}
    assert result.value.source == "provider"


@respx.mock
async def test_adapter_rejects_missing_or_invalid_rates() -> None:
    provider = OpenErApiExchangeRateProvider()
    for payload in (
        {"result": "success", "time_last_update_unix": 1, "rates": {"USD": 1}},
        {"result": "error", "time_last_update_unix": 1, "rates": {"USD": 1, "PEN": 3.4}},
        {"result": "success", "time_last_update_unix": 1, "rates": {"USD": 1, "PEN": 0}},
    ):
        respx.get(PROVIDER_URL).mock(return_value=httpx.Response(200, json=payload))
        result = await provider.fetch_usd_rates()
        assert result.is_failure
        assert result.error.code == "PROVIDER_UNAVAILABLE"

    respx.get(PROVIDER_URL).mock(return_value=httpx.Response(503))
    assert (await provider.fetch_usd_rates()).is_failure


async def test_redis_cache_round_trip() -> None:
    redis = FakeRedis()
    cache = RedisExchangeRateCache(redis)  # type: ignore[arg-type]
    assert await cache.get() is None

    await cache.put(_rates("3.44"), 600)

    assert redis.data[RedisExchangeRateCache.KEY][1] == 600
    assert await cache.get() == _rates("3.44")
