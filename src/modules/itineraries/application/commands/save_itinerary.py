from dataclasses import dataclass
from uuid import UUID

from src.modules.itineraries.domain.model.aggregates.saved_itinerary import (
    SavedItinerary,
)
from src.modules.itineraries.domain.model.value_objects.itinerary_name import (
    ItineraryName,
)
from src.modules.itineraries.domain.model.value_objects.offer_snapshot import (
    OfferSnapshot,
)
from src.modules.itineraries.domain.repositories.saved_itinerary_repository import (
    SavedItineraryRepository,
)
from src.modules.itineraries.domain.services.save_policy import SavePolicy
from src.modules.quotes.interfaces.acl.facade.quotes_facade import QuotesFacade
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.application.unit_of_work import UnitOfWork
from src.shared.domain.domain_error import DomainError


@dataclass(frozen=True, slots=True)
class SaveItineraryCommand:
    user_id: UUID
    search_id: str
    offer_id: str
    name: str | None = None


@dataclass(frozen=True, slots=True)
class SaveItineraryResultDTO:
    itinerary: SavedItinerary
    created: bool


class SaveItineraryHandler:
    def __init__(
        self,
        repo: SavedItineraryRepository,
        quotes_facade: QuotesFacade,
        uow: UnitOfWork,
    ) -> None:
        self._repo = repo
        self._quotes = quotes_facade
        self._uow = uow
        self._policy = SavePolicy()

    async def handle(self, cmd: SaveItineraryCommand) -> Result[SaveItineraryResultDTO]:
        if cmd.name is not None:
            try:
                ItineraryName(cmd.name)
            except DomainError as exc:
                return Result.failure(ApplicationError(code=exc.code, message=exc.message))

        offer_res = await self._quotes.get_offer(
            user_id=cmd.user_id,
            search_id=cmd.search_id,
            offer_id=cmd.offer_id,
        )
        if offer_res.is_failure:
            return Result.failure(offer_res.error)

        offer_dto = offer_res.value
        snapshot = OfferSnapshot(
            offer_id=offer_dto.offer_id,
            trip_type=offer_dto.trip_type,
            origin=offer_dto.origin,
            destination=offer_dto.destination,
            departure_date=offer_dto.departure_date,
            return_date=offer_dto.return_date,
            quoted_at=offer_dto.quoted_at,
            data=offer_dto.snapshot,
        )

        async with self._uow:
            await self._repo.lock_user(cmd.user_id)
            existing = await self._repo.find_by_offer(cmd.user_id, cmd.offer_id)
            if existing is not None:
                return Result.success(SaveItineraryResultDTO(itinerary=existing, created=False))

            current_count = await self._repo.count_for_user(cmd.user_id)
            if not self._policy.can_save(current_count):
                return Result.failure(
                    ApplicationError(
                        code="ITINERARY_LIMIT_REACHED",
                        message="Has alcanzado el límite de 50 itinerarios guardados.",
                    )
                )

            try:
                itinerary = SavedItinerary.save(
                    user_id=cmd.user_id,
                    snapshot=snapshot,
                    name=cmd.name,
                )
            except DomainError as exc:
                return Result.failure(ApplicationError(code=exc.code, message=exc.message))

            await self._repo.add(itinerary)
            await self._uow.commit()
            return Result.success(SaveItineraryResultDTO(itinerary=itinerary, created=True))
