from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

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
from src.modules.itineraries.infrastructure.persistence.models import (
    SavedItineraryModel,
)
from src.shared.infrastructure.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork


class SqlAlchemySavedItineraryRepository(SavedItineraryRepository):
    def __init__(self, session_or_uow: AsyncSession | SqlAlchemyUnitOfWork) -> None:
        self._target = session_or_uow

    @property
    def _session(self) -> AsyncSession:
        if isinstance(self._target, SqlAlchemyUnitOfWork):
            return self._target.session
        return self._target

    @staticmethod
    def _to_domain(row: SavedItineraryModel) -> SavedItinerary:
        raw_quoted = row.offer_snapshot.get("quoted_at")
        if isinstance(raw_quoted, str) and raw_quoted:
            quoted_at = datetime.fromisoformat(raw_quoted.replace("Z", "+00:00"))
        else:
            quoted_at = row.created_at.astimezone(UTC)

        snap = OfferSnapshot(
            offer_id=row.offer_id,
            trip_type=row.trip_type,
            origin=row.origin,
            destination=row.destination,
            departure_date=row.departure_date,
            return_date=row.return_date,
            quoted_at=quoted_at,
            data=dict(row.offer_snapshot),
        )
        return SavedItinerary(
            id=row.id,
            user_id=row.user_id,
            offer_id=row.offer_id,
            name=ItineraryName(row.name),
            trip_type=row.trip_type,
            origin=row.origin,
            destination=row.destination,
            departure_date=row.departure_date,
            return_date=row.return_date,
            offer=snap,
            created_at=row.created_at,
        )

    async def lock_user(self, user_id: UUID) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:u, 0))"),
            {"u": str(user_id)},
        )

    async def add(self, itinerary: SavedItinerary) -> None:
        row = SavedItineraryModel(
            id=itinerary.id,
            user_id=itinerary.user_id,
            offer_id=itinerary.offer_id,
            name=itinerary.name.value,
            trip_type=itinerary.trip_type,
            origin=itinerary.origin,
            destination=itinerary.destination,
            departure_date=itinerary.departure_date,
            return_date=itinerary.return_date,
            offer_snapshot=itinerary.offer.data,
            created_at=itinerary.created_at,
        )
        self._session.add(row)

    async def get(self, itinerary_id: UUID) -> SavedItinerary | None:
        row = await self._session.get(SavedItineraryModel, itinerary_id)
        return self._to_domain(row) if row is not None else None

    async def find_by_offer(self, user_id: UUID, offer_id: str) -> SavedItinerary | None:
        stmt = select(SavedItineraryModel).where(
            SavedItineraryModel.user_id == user_id,
            SavedItineraryModel.offer_id == offer_id,
        )
        res = await self._session.execute(stmt)
        row = res.scalar_one_or_none()
        return self._to_domain(row) if row is not None else None

    async def count_for_user(self, user_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(SavedItineraryModel)
            .where(SavedItineraryModel.user_id == user_id)
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def list_for_user(
        self, user_id: UUID, page: int, page_size: int
    ) -> tuple[list[SavedItinerary], int]:
        total = await self.count_for_user(user_id)
        offset = (page - 1) * page_size
        stmt = (
            select(SavedItineraryModel)
            .where(SavedItineraryModel.user_id == user_id)
            .order_by(
                SavedItineraryModel.created_at.desc(),
                SavedItineraryModel.id.desc(),
            )
            .offset(offset)
            .limit(page_size)
        )
        res = await self._session.execute(stmt)
        items = [self._to_domain(r) for r in res.scalars().all()]
        return items, total

    async def delete(self, itinerary_id: UUID) -> None:
        stmt = delete(SavedItineraryModel).where(SavedItineraryModel.id == itinerary_id)
        await self._session.execute(stmt)

    async def delete_all_for_user(self, user_id: UUID) -> None:
        stmt = delete(SavedItineraryModel).where(SavedItineraryModel.user_id == user_id)
        await self._session.execute(stmt)
