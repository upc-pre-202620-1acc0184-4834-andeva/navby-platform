import asyncio
import logging
from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx

from src.modules.quotes.domain.model.value_objects.flight_offer import LegDirection
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
from src.modules.quotes.infrastructure.adapters.flight_api_translator import (
    translate_flightapi_payload,
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


@respx.mock
async def test_ts28_flightapi_real_oneway_and_roundtrip_payloads() -> None:
    gate = InMemoryProviderGate(max_concurrency=5)
    provider = FlightApiOffersProvider(api_key="test_key", gate=gate, timeout_seconds=1.0)

    # Exact structure returned by https://api.flightapi.io/onewaytrip
    ow_criteria = _sample_criteria(TripType.ONE_WAY)
    ow_pair = AirportPair(origin="LIM", destination="LAX")
    ow_url = "https://api.flightapi.io/onewaytrip/test_key/LIM/LAX/2026-11-01/1/0/0/Economy/USD"
    ow_payload = {
        "itineraries": [
            {
                "id": "12126-2611010600--32317-0-15130-2611011400",
                "leg_ids": ["leg_1"],
                "pricing_options": [
                    {
                        "id": "opt_1",
                        "agent_ids": ["finn"],
                        "price": {"amount": 352.1, "update_status": "current"},
                        "items": [
                            {
                                "agent_id": "finn",
                                "url": "/transport_deeplink/4.0/US/en-GB/USD/finn/1/test",
                                "price": {"amount": 352.1},
                            }
                        ],
                    }
                ],
            }
        ],
        "legs": [
            {
                "id": "leg_1",
                "origin_place_id": 12126,
                "destination_place_id": 15130,
                "departure": "2026-11-01T06:00:00",
                "arrival": "2026-11-01T14:00:00",
                "segment_ids": ["seg_1"],
                "duration": 540,
                "stop_count": 0,
            }
        ],
        "segments": [
            {
                "id": "seg_1",
                "origin_place_id": 12126,
                "destination_place_id": 15130,
                "departure": "2026-11-01T06:00:00",
                "arrival": "2026-11-01T14:00:00",
                "duration": 540,
                "marketing_flight_number": "431",
                "marketing_carrier_id": -32317,
                "operating_carrier_id": -32317,
                "mode": "flight",
            }
        ],
        "places": [
            {"id": 12126, "display_code": "LIM", "name": "Jorge Chavez"},
            {"id": 15130, "display_code": "LAX", "name": "Los Angeles Intl"},
        ],
        "carriers": [
            {"id": -32317, "code": "LA", "name": "LATAM Airlines"},
        ],
    }
    respx.get(ow_url).mock(return_value=httpx.Response(200, json=ow_payload))

    res_ow = await provider.fetch_offers(ow_pair, ow_criteria)
    assert res_ow.is_success
    assert len(res_ow.value) == 1
    ow_offer = res_ow.value[0]
    assert ow_offer.price.amount == Decimal("352.10")
    assert ow_offer.duration_minutes == 540
    assert ow_offer.stops == 0
    assert (
        ow_offer.deep_link
        == "https://www.skyscanner.com/transport_deeplink/4.0/US/en-GB/USD/finn/1/test"
    )
    assert ow_offer.airlines[0].iata == "LA"
    assert ow_offer.legs[0].segments[0].from_iata == "LIM"
    assert ow_offer.legs[0].segments[0].to_iata == "LAX"
    assert ow_offer.legs[0].segments[0].flight_number == "LA431"

    # Roundtrip with stops and dict-keyed places/carriers
    respx.reset()
    rt_criteria = _sample_criteria(TripType.ROUND_TRIP)
    rt_pair = AirportPair(origin="LIM", destination="LAX")
    rt_url = "https://api.flightapi.io/roundtrip/test_key/LIM/LAX/2026-11-01/2026-11-15/1/0/0/Economy/USD"
    rt_payload = {
        "itineraries": [
            {
                "id": "itn_rt_real",
                "leg_ids": ["leg_out", "leg_in"],
                "pricing_options": [
                    {
                        "price": {"amount": 1390.4},
                        "items": [{"url": "/transport_deeplink/4.0/US/en-GB/USD/dela/2/exp"}],
                    },
                    {
                        "price": {"amount": 1250.4},
                        "items": [{"url": "/transport_deeplink/4.0/US/en-GB/USD/dela/2/best"}],
                    },
                ],
            }
        ],
        "legs": [
            {
                "id": "leg_out",
                "departure": "2026-11-01T14:19:00",
                "arrival": "2026-11-02T00:05:00",
                "segment_ids": ["seg_o1", "seg_o2"],
                "duration": 406,
                "stop_count": 1,
            },
            {
                "id": "leg_in",
                "departure": "2026-11-15T15:00:00",
                "arrival": "2026-11-15T19:45:00",
                "segment_ids": ["seg_i1", "seg_i2"],
                "duration": 465,
                "stop_count": 1,
            },
        ],
        "segments": [
            {
                "id": "seg_o1",
                "origin_place_id": 16216,
                "destination_place_id": 9596,
                "departure": "2026-11-01T14:19:00",
                "arrival": "2026-11-01T21:48:00",
                "duration": 269,
                "marketing_flight_number": "437",
                "marketing_carrier_id": -32385,
            },
            {
                "id": "seg_o2",
                "origin_place_id": 9596,
                "destination_place_id": 12387,
                "departure": "2026-11-01T22:25:00",
                "arrival": "2026-11-02T00:05:00",
                "duration": 100,
                "marketing_flight_number": "2178",
                "marketing_carrier_id": -32385,
            },
            {
                "id": "seg_i1",
                "origin_place_id": 12387,
                "destination_place_id": 9596,
                "departure": "2026-11-15T15:00:00",
                "arrival": "2026-11-15T16:38:00",
                "duration": 98,
                "marketing_flight_number": "784",
                "marketing_carrier_id": -32385,
            },
            {
                "id": "seg_i2",
                "origin_place_id": 9596,
                "destination_place_id": 16216,
                "departure": "2026-11-15T17:20:00",
                "arrival": "2026-11-15T19:45:00",
                "duration": 325,
                "marketing_flight_number": "471",
                "marketing_carrier_id": -32385,
            },
        ],
        "places": {
            "16216": {"alt_id": "LIM", "name": "Lima"},
            "9596": {"alt_id": "PTY", "name": "Panama City"},
            "12387": {"alt_id": "LAX", "name": "Los Angeles"},
        },
        "carriers": {
            "-32385": {"display_code": "CM", "name": "Copa Airlines"},
        },
    }
    respx.get(rt_url).mock(return_value=httpx.Response(200, json=rt_payload))

    res_rt = await provider.fetch_offers(rt_pair, rt_criteria)
    assert res_rt.is_success
    assert len(res_rt.value) == 1
    rt_offer = res_rt.value[0]
    assert rt_offer.price.amount == Decimal("1250.40")
    assert rt_offer.duration_minutes == 871
    assert rt_offer.stops == 2
    assert rt_offer.legs[0].direction == LegDirection.OUTBOUND
    assert rt_offer.legs[1].direction == LegDirection.INBOUND
    assert rt_offer.legs[0].segments[0].from_iata == "LIM"
    assert rt_offer.legs[0].segments[1].from_iata == "PTY"
    assert rt_offer.legs[0].segments[1].to_iata == "LAX"
    assert rt_offer.deep_link.endswith("/best")

    # Non-dict JSON fails cleanly as PROVIDER_UNAVAILABLE
    respx.reset()
    respx.get(ow_url).mock(return_value=httpx.Response(200, json=["unexpected"]))
    res_bad = await provider.fetch_offers(ow_pair, ow_criteria)
    assert res_bad.is_failure
    assert res_bad.error.code == "PROVIDER_UNAVAILABLE"


def test_ts28_translator_keeps_legacy_fixture_compatibility() -> None:
    legacy_payload = {
        "itineraries": [
            {
                "id": "legacy_1",
                "leg_ids": ["leg_1"],
                "pricing_options": [
                    {
                        "price": {"amount": 199.0},
                        "items": [{"deep_link": "https://book.navby.example/legacy"}],
                    }
                ],
            }
        ],
        "legs": [
            {
                "id": "leg_1",
                "departure": "2026-11-01T08:00:00",
                "arrival": "2026-11-01T10:00:00",
                "duration_in_minutes": 120,
                "stop_count": 0,
                "segment_ids": ["seg_1"],
            }
        ],
        "segments": [
            {
                "id": "seg_1",
                "departure": "2026-11-01T08:00:00",
                "arrival": "2026-11-01T10:00:00",
                "origin_station_code": "LIM",
                "destination_station_code": "CUZ",
                "marketing_flight_number": "LA2020",
                "marketing_carrier_id": "carrier_la",
            }
        ],
        "carriers": [
            {"id": "carrier_la", "name": "LATAM Airlines", "iata": "LA"},
        ],
    }
    offers = translate_flightapi_payload(legacy_payload, _sample_criteria(TripType.ONE_WAY))
    assert len(offers) == 1
    assert offers[0].duration_minutes == 120
    assert offers[0].deep_link == "https://book.navby.example/legacy"
    assert offers[0].legs[0].segments[0].from_iata == "LIM"
    assert offers[0].legs[0].segments[0].to_iata == "CUZ"
    assert offers[0].legs[0].segments[0].flight_number == "LA2020"
