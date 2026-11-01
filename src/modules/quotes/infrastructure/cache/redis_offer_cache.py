import json
from decimal import Decimal
from typing import Any

from redis.asyncio import Redis

from src.modules.quotes.application.acl.ports.offer_cache import OfferCache
from src.modules.quotes.domain.model.value_objects.flight_offer import (
    AirlineInfo,
    FlightOffer,
    Leg,
    LegDirection,
    Money,
    Segment,
)


def serialize_offer(offer: FlightOffer) -> dict[str, Any]:
    return {
        "offer_id": offer.offer_id,
        "price": {
            "amount": offer.price.formatted(),
            "currency": offer.price.currency,
        },
        "duration_minutes": offer.duration_minutes,
        "stops": offer.stops,
        "deep_link": offer.deep_link,
        "airlines": [{"iata": a.iata, "name": a.name, "logo": a.logo} for a in offer.airlines],
        "legs": [
            {
                "direction": leg.direction.value,
                "departure": leg.departure,
                "arrival": leg.arrival,
                "duration_minutes": leg.duration_minutes,
                "stops": leg.stops,
                "segments": [
                    {
                        "from_iata": seg.from_iata,
                        "to_iata": seg.to_iata,
                        "departure": seg.departure,
                        "arrival": seg.arrival,
                        "flight_number": seg.flight_number,
                        "airline_iata": seg.airline_iata,
                    }
                    for seg in leg.segments
                ],
            }
            for leg in offer.legs
        ],
    }


def deserialize_offer(data: dict[str, Any]) -> FlightOffer:
    legs = tuple(
        Leg(
            direction=LegDirection(str(leg_raw["direction"])),
            departure=str(leg_raw["departure"]),
            arrival=str(leg_raw["arrival"]),
            duration_minutes=int(leg_raw["duration_minutes"]),
            stops=int(leg_raw["stops"]),
            segments=tuple(
                Segment(
                    from_iata=str(s["from_iata"]),
                    to_iata=str(s["to_iata"]),
                    departure=str(s["departure"]),
                    arrival=str(s["arrival"]),
                    flight_number=str(s["flight_number"]),
                    airline_iata=str(s["airline_iata"]),
                )
                for s in leg_raw["segments"]
            ),
        )
        for leg_raw in data["legs"]
    )
    airlines = tuple(
        AirlineInfo(
            iata=str(a["iata"]),
            name=str(a["name"]),
            logo=str(a.get("logo", "")),
        )
        for a in data["airlines"]
    )
    return FlightOffer(
        offer_id=str(data["offer_id"]),
        price=Money(
            amount=Decimal(str(data["price"]["amount"])),
            currency=str(data["price"]["currency"]),
        ),
        duration_minutes=int(data["duration_minutes"]),
        stops=int(data["stops"]),
        legs=legs,
        airlines=airlines,
        deep_link=str(data["deep_link"]),
    )


class RedisOfferCache(OfferCache):
    TTL_SECONDS = 1800

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, pair_key: str) -> list[FlightOffer] | None:
        key = f"navby:quotes:offers:{pair_key}"
        raw = await self._redis.get(key)
        if not raw:
            return None
        items = json.loads(str(raw))
        return [deserialize_offer(item) for item in items]

    async def put(self, pair_key: str, offers: list[FlightOffer]) -> None:
        if not offers:
            return
        key = f"navby:quotes:offers:{pair_key}"
        payload = json.dumps([serialize_offer(o) for o in offers])
        await self._redis.set(key, payload, ex=self.TTL_SECONDS)
