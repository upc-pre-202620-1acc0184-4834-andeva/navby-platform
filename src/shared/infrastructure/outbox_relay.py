import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.shared.domain.integration_event import IntegrationEvent
from src.shared.infrastructure.in_memory_event_bus import InMemoryEventBus
from src.shared.infrastructure.outbox_model import OutboxModel

logger = logging.getLogger(__name__)

EventDeserializer = Callable[[UUID, datetime, dict[str, Any]], IntegrationEvent]


@dataclass(frozen=True, slots=True)
class GenericOutboxEvent(IntegrationEvent):
    event_type: ClassVar[str] = "generic"
    actual_event_type: str
    data: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return dict(self.data)


class OutboxRelay:
    MAX_ATTEMPTS = 5
    BATCH_SIZE = 50

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        event_bus: InMemoryEventBus,
    ) -> None:
        self._session_factory = session_factory
        self._event_bus = event_bus
        self._deserializers: dict[str, EventDeserializer] = {}

    def register_event_type(self, event_type: str, deserializer: EventDeserializer) -> None:
        self._deserializers[event_type] = deserializer

    async def process_pending_batch(self) -> int:
        processed_count = 0
        async with self._session_factory() as session:
            stmt = (
                select(OutboxModel)
                .where(
                    OutboxModel.processed_at.is_(None),
                    OutboxModel.failed_at.is_(None),
                )
                .order_by(OutboxModel.occurred_at.asc())
                .limit(self.BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
            result = await session.execute(stmt)
            rows = list(result.scalars().all())

            for row in rows:
                now = datetime.now(UTC)
                try:
                    event = self._deserialize(row)
                    await self._event_bus.publish(event)
                    row.processed_at = now
                    processed_count += 1
                except Exception as exc:
                    row.attempts += 1
                    row.last_error = str(exc)
                    if row.attempts >= self.MAX_ATTEMPTS:
                        row.failed_at = now
                        logger.critical(
                            "Outbox event poisoned after %d attempts: event_type=%s id=%s error=%s",
                            row.attempts,
                            row.event_type,
                            row.id,
                            exc,
                        )
            await session.commit()
        return processed_count

    def _deserialize(self, row: OutboxModel) -> IntegrationEvent:
        deserializer = self._deserializers.get(row.event_type)
        if deserializer is not None:
            return deserializer(row.id, row.occurred_at, row.payload)

        @dataclass(frozen=True, slots=True)
        class DynamicIntegrationEvent(IntegrationEvent):
            event_type: ClassVar[str] = row.event_type
            raw_payload: dict[str, Any]

            def to_payload(self) -> dict[str, Any]:
                return dict(self.raw_payload)

        return DynamicIntegrationEvent(
            event_id=row.id,
            occurred_at=row.occurred_at,
            raw_payload=row.payload,
        )

    @staticmethod
    async def retry_event(
        session_factory: async_sessionmaker[AsyncSession],
        event_id: UUID,
    ) -> bool:
        async with session_factory() as session:
            row = await session.get(OutboxModel, event_id)
            if row is None:
                return False
            row.failed_at = None
            row.attempts = 0
            row.last_error = None
            await session.commit()
            return True
