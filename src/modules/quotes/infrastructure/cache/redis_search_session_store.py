import json
from datetime import date, datetime
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

from src.modules.quotes.application.acl.ports.search_session_store import (
    SearchSessionStore,
)
from src.modules.quotes.domain.model.aggregates.quote_search import QuoteSearch
from src.modules.quotes.domain.model.value_objects.preference_weights import (
    PreferenceProfile,
    PreferenceWeights,
)
from src.modules.quotes.domain.model.value_objects.search_criteria import (
    AirportPair,
    Cabin,
    Currency,
    PassengerMix,
    SearchCriteria,
    TripType,
)
from src.modules.quotes.domain.model.value_objects.search_id import SearchId
from src.modules.quotes.domain.services.multicriteria_ranker import MulticriteriaRanker
from src.modules.quotes.infrastructure.cache.redis_offer_cache import (
    deserialize_offer,
    serialize_offer,
)


class RedisSearchSessionStore(SearchSessionStore):
    TTL_SECONDS = 1800

    def __init__(self, redis: Redis) -> None:
        self._redis: Any = redis

    async def ping(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except Exception:
            return False

    @staticmethod
    def _serialize(search: QuoteSearch) -> str:
        c = search.criteria
        payload = {
            "search_id": search.id.value,
            "user_id": str(search.user_id),
            "criteria": {
                "trip_type": c.trip_type.value,
                "origins": list(c.origins),
                "destinations": list(c.destinations),
                "departure_date": c.departure_date.isoformat(),
                "return_date": (c.return_date.isoformat() if c.return_date is not None else None),
                "passengers": {
                    "adults": c.passengers.adults,
                    "children": c.passengers.children,
                    "infants": c.passengers.infants,
                },
                "cabin": c.cabin.value,
                "currency": c.currency.value,
            },
            "pairs_quoted": [
                {"origin": p.origin, "destination": p.destination} for p in search.pairs_quoted
            ],
            "pareto_front": [serialize_offer(o) for o in search.pareto_front],
            "offers_received": search.offers_received,
            "t_min_minutes": search.t_min_minutes,
            "weights": {
                "profile": search.weights.profile.value,
                "price": search.weights.price,
                "duration": search.weights.duration,
                "stops": search.weights.stops,
            },
            "partial": search.partial,
            "credits_charged": search.credits_charged,
            "credits_remaining": search.credits_remaining,
            "created_at": search.created_at.isoformat(),
            "expires_at": search.expires_at.isoformat(),
        }
        return json.dumps(payload)

    @staticmethod
    def _deserialize(raw: str) -> QuoteSearch:
        data = json.loads(raw)
        c_raw = data["criteria"]
        pax_raw = c_raw["passengers"]
        criteria = SearchCriteria(
            trip_type=TripType(str(c_raw["trip_type"])),
            origins=tuple(str(x) for x in c_raw["origins"]),
            destinations=tuple(str(x) for x in c_raw["destinations"]),
            departure_date=date.fromisoformat(str(c_raw["departure_date"])),
            return_date=(
                date.fromisoformat(str(c_raw["return_date"]))
                if c_raw["return_date"] is not None
                else None
            ),
            passengers=PassengerMix(
                adults=int(pax_raw["adults"]),
                children=int(pax_raw["children"]),
                infants=int(pax_raw["infants"]),
            ),
            cabin=Cabin(str(c_raw["cabin"])),
            currency=Currency(str(c_raw["currency"])),
            today_lima=None,
        )
        pairs_quoted = tuple(
            AirportPair(origin=str(p["origin"]), destination=str(p["destination"]))
            for p in data["pairs_quoted"]
        )
        pareto_front = [deserialize_offer(o) for o in data["pareto_front"]]
        w_raw = data["weights"]
        weights = PreferenceWeights(
            profile=PreferenceProfile(str(w_raw["profile"])),
            price=float(w_raw["price"]),
            duration=float(w_raw["duration"]),
            stops=float(w_raw["stops"]),
        )
        podium = MulticriteriaRanker().rank(pareto_front, weights)
        return QuoteSearch(
            id=SearchId(str(data["search_id"])),
            user_id=UUID(str(data["user_id"])),
            criteria=criteria,
            pairs_quoted=pairs_quoted,
            pareto_front=pareto_front,
            offers_received=int(data["offers_received"]),
            t_min_minutes=int(data["t_min_minutes"]),
            weights=weights,
            podium=podium,
            partial=bool(data["partial"]),
            credits_charged=int(data["credits_charged"]),
            credits_remaining=int(data["credits_remaining"]),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            expires_at=datetime.fromisoformat(str(data["expires_at"])),
        )

    async def get(self, search_id: SearchId) -> QuoteSearch | None:
        key = f"navby:quotes:search:{search_id.value}"
        raw = await self._redis.get(key)
        if not raw:
            return None
        return self._deserialize(str(raw))

    async def create(self, search: QuoteSearch) -> None:
        key = f"navby:quotes:search:{search.id.value}"
        await self._redis.set(key, self._serialize(search), ex=self.TTL_SECONDS)

    async def update(self, search: QuoteSearch) -> None:
        key = f"navby:quotes:search:{search.id.value}"
        await self._redis.set(key, self._serialize(search), keepttl=True)
