from dataclasses import dataclass
from uuid import UUID

from src.modules.itineraries.domain.repositories.saved_itinerary_repository import (
    SavedItineraryRepository,
)
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.application.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class DeleteItineraryCommand:
    user_id: UUID
    itinerary_id: UUID


class DeleteItineraryHandler:
    def __init__(
        self,
        repo: SavedItineraryRepository,
        uow: UnitOfWork,
    ) -> None:
        self._repo = repo
        self._uow = uow

    async def handle(self, cmd: DeleteItineraryCommand) -> Result[None]:
        async with self._uow:
            itinerary = await self._repo.get(cmd.itinerary_id)
            if itinerary is None or not itinerary.is_owned_by(cmd.user_id):
                return Result.failure(
                    ApplicationError(
                        code="ITINERARY_NOT_FOUND",
                        message="El itinerario no existe.",
                    )
                )
            await self._repo.delete(cmd.itinerary_id)
            await self._uow.commit()
            return Result.success(None)
