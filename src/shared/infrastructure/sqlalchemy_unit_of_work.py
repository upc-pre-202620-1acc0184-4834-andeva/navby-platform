from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.shared.domain.aggregate_root import AggregateRoot
from src.shared.domain.integration_event import IntegrationEvent
from src.shared.infrastructure.outbox_model import OutboxModel


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._tracked_aggregates: list[AggregateRoot] = []

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("UnitOfWork session is not active.")
        return self._session

    def track(self, aggregate: AggregateRoot) -> None:
        if aggregate not in self._tracked_aggregates:
            self._tracked_aggregates.append(aggregate)

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self._tracked_aggregates.clear()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._session is not None:
            if exc_type is not None:
                await self._session.rollback()
            await self._session.close()
            self._session = None
        self._tracked_aggregates.clear()

    async def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("UnitOfWork session is not active.")
        for aggregate in self._tracked_aggregates:
            for event in aggregate.pull_events():
                if isinstance(event, IntegrationEvent):
                    self._session.add(
                        OutboxModel(
                            id=event.event_id,
                            event_type=event.event_type,
                            payload=event.to_payload(),
                            occurred_at=event.occurred_at,
                        )
                    )
        await self._session.commit()
        self._tracked_aggregates.clear()

    async def rollback(self) -> None:
        if self._session is not None:
            await self._session.rollback()
        self._tracked_aggregates.clear()
