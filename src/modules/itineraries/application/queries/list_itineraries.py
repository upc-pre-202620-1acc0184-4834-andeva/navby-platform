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
class ListItinerariesQuery:
    user_id: UUID
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True, slots=True)
class PaginatedItinerariesDTO:
    items: list[SavedItinerary]
    page: int
    page_size: int
    total: int


class ListItinerariesHandler:
    def __init__(self, repo: SavedItineraryRepository) -> None:
        self._repo = repo

    async def handle(self, query: ListItinerariesQuery) -> Result[PaginatedItinerariesDTO]:
        if query.page < 1 or not (1 <= query.page_size <= 50):
            return Result.failure(
                ApplicationError(
                    code="VALIDATION_ERROR",
                    message="Parámetros de paginación inválidos.",
                )
            )
        items, total = await self._repo.list_for_user(
            user_id=query.user_id,
            page=query.page,
            page_size=query.page_size,
        )
        return Result.success(
            PaginatedItinerariesDTO(
                items=items,
                page=query.page,
                page_size=query.page_size,
                total=total,
            )
        )
