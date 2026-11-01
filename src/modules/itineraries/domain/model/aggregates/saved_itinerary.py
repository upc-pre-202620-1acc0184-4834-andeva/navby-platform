from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from src.modules.itineraries.domain.model.value_objects.itinerary_name import (
    ItineraryName,
)
from src.modules.itineraries.domain.model.value_objects.offer_snapshot import (
    OfferSnapshot,
)
from src.shared.domain.aggregate_root import AggregateRoot


class SavedItinerary(AggregateRoot):
    def __init__(
        self,
        id: UUID,
        user_id: UUID,
        offer_id: str,
        name: ItineraryName,
        trip_type: str,
        origin: str,
        destination: str,
        departure_date: date,
        return_date: date | None,
        offer: OfferSnapshot,
        created_at: datetime,
    ) -> None:
        super().__init__()
        self.id = id
        self.user_id = user_id
        self.offer_id = offer_id
        self.name = name
        self.trip_type = trip_type
        self.origin = origin
        self.destination = destination
        self.departure_date = departure_date
        self.return_date = return_date
        self.offer = offer
        self.created_at = created_at

    @staticmethod
    def save(
        user_id: UUID,
        snapshot: OfferSnapshot,
        name: str | None = None,
        now: datetime | None = None,
    ) -> "SavedItinerary":
        ts = now or datetime.now(UTC)
        default_name = (
            f"{snapshot.origin} \u2192 {snapshot.destination} "
            f"\u00b7 {snapshot.departure_date.isoformat()}"
        )
        raw_name = name if name is not None and name.strip() else default_name
        itin_name = ItineraryName(raw_name)
        return SavedItinerary(
            id=uuid4(),
            user_id=user_id,
            offer_id=snapshot.offer_id,
            name=itin_name,
            trip_type=snapshot.trip_type,
            origin=snapshot.origin,
            destination=snapshot.destination,
            departure_date=snapshot.departure_date,
            return_date=snapshot.return_date,
            offer=snapshot,
            created_at=ts,
        )

    def is_owned_by(self, user_id: UUID) -> bool:
        return self.user_id == user_id
