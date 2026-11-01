from typing import Protocol

from src.modules.quotes.domain.model.value_objects.flight_offer import FlightOffer
from src.modules.quotes.domain.model.value_objects.search_criteria import (
    AirportPair,
    SearchCriteria,
)
from src.shared.application.result import Result


class FlightOffersProvider(Protocol):
    async def fetch_offers(
        self, pair: AirportPair, criteria: SearchCriteria
    ) -> Result[list[FlightOffer]]: ...
