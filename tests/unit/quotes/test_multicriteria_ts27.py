import math
from decimal import Decimal

import pytest

from src.modules.quotes.domain.model.value_objects.flight_offer import (
    AirlineInfo,
    FlightOffer,
    Leg,
    LegDirection,
    Money,
    Segment,
)
from src.modules.quotes.domain.model.value_objects.preference_weights import (
    PreferenceProfile,
    PreferenceWeights,
)
from src.modules.quotes.domain.services.multicriteria_ranker import MulticriteriaRanker
from src.modules.quotes.domain.services.pareto_filter import ParetoFilter


def _make_offer(
    offer_id: str,
    price: float,
    duration: int,
    stops: int,
    departure: str = "2026-11-01T08:00:00",
    airports: tuple[str, ...] = ("LIM", "MIA"),
    airline: str = "LA",
) -> FlightOffer:
    segments = []
    for idx in range(len(airports) - 1):
        segments.append(
            Segment(
                from_iata=airports[idx],
                to_iata=airports[idx + 1],
                departure=departure,
                arrival="2026-11-01T14:00:00",
                flight_number=f"{airline}10{idx}",
                airline_iata=airline,
            )
        )
    leg = Leg(
        direction=LegDirection.OUTBOUND,
        departure=departure,
        arrival="2026-11-01T14:00:00",
        duration_minutes=duration,
        stops=stops,
        segments=tuple(segments),
    )
    return FlightOffer(
        offer_id=offer_id,
        price=Money(amount=Decimal(f"{price:.2f}"), currency="USD"),
        duration_minutes=duration,
        stops=stops,
        legs=(leg,),
        airlines=(AirlineInfo(iata=airline, name=f"Airline {airline}", logo=""),),
        deep_link=f"https://book.example/{offer_id}",
    )


def test_ts27_pareto_dominance_and_identical_tiebreak() -> None:
    pf = ParetoFilter()
    a = _make_offer("off_a", 100.0, 300, 1)
    b = _make_offer("off_b", 120.0, 320, 1)
    dup1 = _make_offer("off_z", 100.0, 300, 1)

    front = pf.filter([b, dup1, a])
    assert [o.offer_id for o in front] == ["off_a"]


def test_ts27_normalization_and_balanced_score() -> None:
    ranker = MulticriteriaRanker()
    o1 = _make_offer("off_1", 100.0, 600, 1, airports=("LIM", "PTY", "MIA"), airline="CM")
    o2 = _make_offer("off_2", 200.0, 300, 1, airports=("LIM", "BOG", "MIA"), airline="AV")

    weights = PreferenceWeights.from_profile(PreferenceProfile.BALANCED)
    podium = ranker.rank([o1, o2], weights)
    assert len(podium) == 2

    by_id = {r.offer.offer_id: r for r in podium}
    # For o1 (100, 600): p' = 0, t' = 1, e' = 0 -> S = sqrt(0.3 * 1^2) = sqrt(0.3)
    assert math.isclose(by_id["off_1"].score, math.sqrt(0.3), rel_tol=1e-6)
    assert by_id["off_1"].match_pct == round((1.0 - math.sqrt(0.3)) * 100)


def test_ts27_tiebreaks_and_diversity() -> None:
    ranker = MulticriteriaRanker()
    weights = PreferenceWeights.from_profile(PreferenceProfile.BALANCED)

    # Same airport sequence + same airline -> only 1 enters podium
    same_1 = _make_offer(
        "off_1",
        150.0,
        350,
        0,
        departure="2026-11-01T07:00:00",
        airports=("LIM", "MIA"),
        airline="LA",
    )
    same_2 = _make_offer(
        "off_2",
        140.0,
        360,
        0,
        departure="2026-11-01T12:00:00",
        airports=("LIM", "MIA"),
        airline="LA",
    )
    # Direct flight LIM-MIA on a DIFFERENT airline -> CAN enter podium together!
    diff_airline = _make_offer(
        "off_3",
        145.0,
        355,
        0,
        departure="2026-11-01T09:00:00",
        airports=("LIM", "MIA"),
        airline="AA",
    )

    pf = ParetoFilter()
    front = pf.filter([same_1, same_2, diff_airline])
    podium = ranker.rank(front, weights)
    ids = [r.offer.offer_id for r in podium]
    assert "off_3" in ids
    assert sum(1 for i in ids if i in {"off_1", "off_2"}) == 1


def test_ts27_edge_cases_empty_and_single_offer() -> None:
    ranker = MulticriteriaRanker()
    weights = PreferenceWeights.from_profile(PreferenceProfile.BALANCED)

    assert ranker.rank([], weights) == []

    single = _make_offer("only_1", 250.0, 400, 0)
    res = ranker.rank([single], weights)
    assert len(res) == 1
    assert res[0].rank == 1
    assert res[0].score == pytest.approx(0.0)
    assert res[0].match_pct == 100
