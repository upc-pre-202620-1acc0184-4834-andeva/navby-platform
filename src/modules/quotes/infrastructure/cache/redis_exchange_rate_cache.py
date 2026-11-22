import json
from datetime import datetime
from decimal import Decimal

from redis.asyncio import Redis

from src.modules.quotes.application.acl.ports.exchange_rate_cache import (
    ExchangeRateCache,
)
from src.modules.quotes.domain.model.value_objects.exchange_rates import ExchangeRates


class RedisExchangeRateCache(ExchangeRateCache):
    KEY = "navby:quotes:fx:usd"

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self) -> ExchangeRates | None:
        raw = await self._redis.get(self.KEY)
        if not raw:
            return None
        data = json.loads(str(raw))
        return ExchangeRates(
            rates={code: Decimal(value) for code, value in data["rates"].items()},
            as_of=datetime.fromisoformat(data["as_of"]),
            source=str(data["source"]),
        )

    async def put(self, rates: ExchangeRates, ttl_seconds: int) -> None:
        payload = json.dumps(
            {
                "rates": {code: str(value) for code, value in rates.rates.items()},
                "as_of": rates.as_of.isoformat(),
                "source": rates.source,
            }
        )
        await self._redis.set(self.KEY, payload, ex=ttl_seconds)
