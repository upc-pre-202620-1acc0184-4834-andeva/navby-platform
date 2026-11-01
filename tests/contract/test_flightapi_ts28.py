import asyncio
import logging
from datetime import date

import httpx
import pytest
import respx

from src.modules.quotes.domain.model.value_objects.search_criteria import (
    AirportPair,
    Cabin,
    Currency,
    PassengerMix,
    SearchCriteria,
    TripType,
)
from src.modules.quotes.infrastructure.adapters.flight_api_offers_provider import (
    FlightApiOffersProvider,
)
from src.modules.quotes.infrastructure.adapters.in_memory_provider_gate import (
    InMemoryProviderGate,
)
from src.modules.quotes.infrastructure.adapters.mock_flight_offers_provider import (
    MockFlightOffersProvider,
)


def _sample_criteria(trip_type: TripType = TripType.ROUND_TRIP) -> SearchCriteria:
    return SearchCriteria(
        trip_type=trip_type,
        origins=("LIM",),
        destinations=("MIA",),
        departure_date=date(2026, 11, 1),
        return_date=date(2026, 11, 15) if trip_type == TripType.ROUND_TRIP else None,
        passengers=PassengerMix(adults=1, children=0, infants=0),
        cabin=Cabin.ECONOMY,
        currency=Currency.USD,
        today_lima=date(2026, 10, 15),
    )


async def test_ts28_mock_provider_deterministic_and_filtering() -> None:
    provider = MockFlightOffersProvider()
    criteria = _sample_criteria(TripType.ROUND_TRIP)
    pair = AirportPair(origin="LIM", destination="MIA")

    res1 = await provider.fetch_offers(pair, criteria)
    res2 = await provider.fetch_offers(pair, criteria)
    assert res1.is_success and res2.is_success
    offers1 = res1.value
    offers2 = res2.value
    assert len(offers1) >= 3
    assert [o.offer_id for o in offers1] == [o.offer_id for o in offers2]

    for offer in offers1:
        assert len(offer.offer_id) == 16
        assert offer.price.amount > 0
        assert offer.deep_link.startswith("https://")
        assert len(offer.legs) == 2
        assert all(leg.stops <= 2 for leg in offer.legs)
        assert offer.duration_minutes == sum(leg.duration_minutes for leg in offer.legs)
        assert offer.stops == sum(leg.stops for leg in offer.legs)


@respx.mock
async def test_ts28_flightapi_provider_5xx_retry_4xx_log_and_timeout(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gate = InMemoryProviderGate(max_concurrency=5)
    provider = FlightApiOffersProvider(api_key="test_key", gate=gate, timeout_seconds=0.2)
    criteria = _sample_criteria(TripType.ONE_WAY)
    pair = AirportPair(origin="LIM", destination="MIA")
    url = "https://api.flightapi.io/onewaytrip/test_key/LIM/MIA/2026-11-01/1/0/0/Economy/USD"

    # 5xx -> 1 immediate retry, then fail
    route_500 = respx.get(url).mock(
        side_effect=[
            httpx.Response(502, json={"error": "bad gateway"}),
            httpx.Response(503, json={"error": "unavailable"}),
        ]
    )
    r_5xx = await provider.fetch_offers(pair, criteria)
    assert r_5xx.is_failure
    assert route_500.call_count == 2

    # 402 / 429 -> no retry, logs ERROR
    respx.reset()
    route_429 = respx.get(url).mock(return_value=httpx.Response(429, json={"error": "quota"}))
    caplog.set_level(logging.ERROR)
    r_429 = await provider.fetch_offers(pair, criteria)
    assert r_429.is_failure
    assert route_429.call_count == 1
    assert any(rec.levelname == "ERROR" for rec in caplog.records)

    # Timeout -> no retry
    respx.reset()
    route_timeout = respx.get(url).mock(side_effect=httpx.ReadTimeout("timed out"))
    r_to = await provider.fetch_offers(pair, criteria)
    assert r_to.is_failure
    assert route_timeout.call_count == 1


async def test_ts28_concurrency_semaphore_limit_and_wait_timeout() -> None:
    gate = InMemoryProviderGate(max_concurrency=5, wait_timeout_seconds=0.15)
    active = 0
    max_seen = 0

    async def worker(hold_time: float) -> bool:
        nonlocal active, max_seen
        try:
            async with gate.slot():
                active += 1
                max_seen = max(max_seen, active)
                await asyncio.sleep(hold_time)
                active -= 1
                return True
        except TimeoutError:
            return False

    results = await asyncio.gather(*(worker(0.3) for _ in range(8)))
    assert max_seen <= 5
    assert results.count(True) == 5
    assert results.count(False) == 3
