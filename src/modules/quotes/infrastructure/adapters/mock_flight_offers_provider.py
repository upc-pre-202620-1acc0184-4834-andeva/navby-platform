import json
from pathlib import Path
from typing import Any

from src.modules.quotes.application.acl.ports.flight_offers_provider import (
    FlightOffersProvider,
)
from src.modules.quotes.domain.model.value_objects.flight_offer import FlightOffer
from src.modules.quotes.domain.model.value_objects.search_criteria import (
    AirportPair,
    SearchCriteria,
    TripType,
)
from src.modules.quotes.infrastructure.adapters.flight_api_translator import (
    translate_flightapi_payload,
)
from src.shared.application.result import Result


class MockFlightOffersProvider(FlightOffersProvider):
    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._fixtures_dir = fixtures_dir or (
            Path(__file__).resolve().parents[5] / "fixtures" / "flightapi"
        )

    def _load_fixture_json(self, pair: AirportPair, criteria: SearchCriteria) -> dict[str, Any]:
        trip_suffix = "roundtrip" if criteria.trip_type == TripType.ROUND_TRIP else "oneway"
        specific = self._fixtures_dir / f"{pair.origin}_{pair.destination}_{trip_suffix}.json"
        default_file = self._fixtures_dir / f"default_{trip_suffix}.json"
        target = specific if specific.exists() else default_file
        raw_text = target.read_text(encoding="utf-8")
        rendered = raw_text.replace("{ORIGIN}", pair.origin).replace(
            "{DESTINATION}", pair.destination
        )
        return dict(json.loads(rendered))

    async def fetch_offers(
        self, pair: AirportPair, criteria: SearchCriteria
    ) -> Result[list[FlightOffer]]:
        payload = self._load_fixture_json(pair, criteria)
        offers = translate_flightapi_payload(payload, criteria)
        return Result.success(offers)
