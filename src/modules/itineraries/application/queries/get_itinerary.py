from dataclasses import dataclass
from uuid import UUID

from src.modules.itineraries.domain.model.aggregates.saved_itinerary import (
    SavedItinerary,
)
from src.modules.itineraries.domain.repositories.saved_itinerary_repository import (
    SavedItineraryRepository,
)
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result


@dataclass(frozen=True, slots=True)
class GetItineraryQuery:
    user_id: UUID
    itinerary_id: UUID


class GetItineraryHandler:
    def __init__(self, repo: SavedItineraryRepository) -> None:
        self._repo = repo

    async def handle(self, query: GetItineraryQuery) -> Result[SavedItinerary]:
        itinerary = await self._repo.get(query.itinerary_id)
        if itinerary is None or not itinerary.is_owned_by(query.user_id):
            return Result.failure(
                ApplicationError(
                    code="ITINERARY_NOT_FOUND",
                    message="El itinerario no existe.",
                )
            )
        return Result.success(itinerary)
