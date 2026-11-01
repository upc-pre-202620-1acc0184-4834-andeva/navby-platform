from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class OfferSnapshot:
    offer_id: str
    trip_type: str
    origin: str
    destination: str
    departure_date: date
    return_date: date | None
    quoted_at: datetime
    data: dict[str, Any]
