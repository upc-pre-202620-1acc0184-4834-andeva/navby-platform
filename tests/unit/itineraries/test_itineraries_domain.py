from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from src.modules.itineraries.domain.model.aggregates.saved_itinerary import (
    SavedItinerary,
)
from src.modules.itineraries.domain.model.value_objects.itinerary_name import (
    ItineraryName,
)
from src.modules.itineraries.domain.model.value_objects.offer_snapshot import (
    OfferSnapshot,
)
from src.modules.itineraries.domain.services.save_policy import SavePolicy
from src.shared.domain.domain_error import DomainError


def test_itinerary_name_and_save_policy() -> None:
    policy = SavePolicy()
    assert policy.can_save(0) is True
    assert policy.can_save(49) is True
    assert policy.can_save(50) is False

    name = ItineraryName("Japón 2026")
    assert name.value == "Japón 2026"

    with pytest.raises(DomainError) as exc:
        ItineraryName("   ")
    assert exc.value.code == "VALIDATION_ERROR"

    with pytest.raises(DomainError) as exc2:
        ItineraryName("x" * 81)
    assert exc2.value.code == "VALIDATION_ERROR"

    now = datetime.now(UTC)
    snap = OfferSnapshot(
        offer_id="9f2c41ab07d3e655",
        trip_type="ROUND_TRIP",
        origin="LIM",
        destination="HND",
        departure_date=date(2026, 11, 1),
        return_date=date(2026, 11, 15),
        quoted_at=now,
        data={"offer_id": "9f2c41ab07d3e655", "quoted_at": "2026-10-15T15:00:00Z"},
    )
    itin = SavedItinerary.save(user_id=uuid4(), snapshot=snap, name=None, now=now)
    assert itin.name.value == "LIM \u2192 HND \u00b7 2026-11-01"
