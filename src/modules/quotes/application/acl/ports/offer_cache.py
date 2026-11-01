from typing import Protocol

from src.modules.quotes.domain.model.value_objects.flight_offer import FlightOffer


class OfferCache(Protocol):
    async def get(self, pair_key: str) -> list[FlightOffer] | None: ...

    async def put(self, pair_key: str, offers: list[FlightOffer]) -> None: ...
