from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.iam.domain.model.events.user_deleted import UserDeleted
from src.modules.itineraries.infrastructure.persistence.models import (
    SavedItineraryModel,
)
from src.shared.domain.integration_event import IntegrationEvent


class DeleteUserItinerariesHandler:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def handle(self, event: IntegrationEvent) -> None:
        if isinstance(event, UserDeleted):
            user_id = event.user_id
        else:
            user_id = UUID(str(event.to_payload()["user_id"]))

        async with self._session_factory() as session:
            stmt = delete(SavedItineraryModel).where(SavedItineraryModel.user_id == user_id)
            await session.execute(stmt)
            await session.commit()
