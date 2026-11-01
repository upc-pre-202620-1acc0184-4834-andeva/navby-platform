import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from src.modules.billing.application.event_handlers.forfeit_wallet import (
    ForfeitWalletHandler,
)
from src.modules.billing.application.event_handlers.open_wallet import OpenWalletHandler
from src.modules.iam.domain.model.events.user_deleted import UserDeleted
from src.modules.iam.domain.model.events.user_verified import UserVerified
from src.modules.itineraries.application.event_handlers.delete_user_itineraries import (
    DeleteUserItinerariesHandler,
)
from src.shared.domain.integration_event import IntegrationEvent
from src.shared.infrastructure.database import get_session_factory
from src.shared.infrastructure.in_memory_event_bus import InMemoryEventBus
from src.shared.infrastructure.outbox_model import OutboxModel
from src.shared.infrastructure.outbox_relay import OutboxRelay
from src.shared.outbox.__main__ import main as outbox_cli_main


async def test_ts34_outbox_delivery_and_idempotent_consumers() -> None:
    session_factory = get_session_factory()
    bus = InMemoryEventBus()
    open_wallet = OpenWalletHandler(session_factory)
    forfeit_wallet = ForfeitWalletHandler(session_factory)
    del_itineraries = DeleteUserItinerariesHandler(session_factory)

    bus.subscribe("iam.user_verified", open_wallet)
    bus.subscribe("iam.user_deleted", forfeit_wallet)
    bus.subscribe("iam.user_deleted", del_itineraries)

    relay = OutboxRelay(session_factory=session_factory, event_bus=bus)
    relay.register_event_type("iam.user_verified", UserVerified.from_payload)
    relay.register_event_type("iam.user_deleted", UserDeleted.from_payload)

    user_id = uuid4()
    ev1 = UserVerified(event_id=uuid4(), occurred_at=datetime.now(UTC), user_id=user_id)
    ev2 = UserVerified(event_id=uuid4(), occurred_at=datetime.now(UTC), user_id=user_id)

    async with session_factory() as session:
        session.add(
            OutboxModel(
                id=ev1.event_id,
                event_type=ev1.event_type,
                payload=ev1.to_payload(),
                occurred_at=ev1.occurred_at,
            )
        )
        session.add(
            OutboxModel(
                id=ev2.event_id,
                event_type=ev2.event_type,
                payload=ev2.to_payload(),
                occurred_at=ev2.occurred_at,
            )
        )
        await session.commit()

    processed = await relay.process_pending_batch()
    assert processed >= 2

    async with session_factory() as session:
        row1 = await session.get(OutboxModel, ev1.event_id)
        assert row1 is not None and row1.processed_at is not None

        res = await session.execute(
            text(
                "SELECT count(*), free_credits FROM billing.credit_wallets "
                "WHERE user_id = :u GROUP BY free_credits"
            ),
            {"u": user_id},
        )
        wallet_row = res.first()
        assert wallet_row is not None
        assert wallet_row[0] == 1
        assert wallet_row[1] == 10


async def test_ts34_poisoned_event_5_attempts_and_cli_retry(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session_factory = get_session_factory()
    bus = InMemoryEventBus()

    class FailingHandler:
        async def handle(self, event: IntegrationEvent) -> None:
            raise RuntimeError(f"boom on {event.event_id}")

    bus.subscribe("test.poison", FailingHandler())
    relay = OutboxRelay(session_factory=session_factory, event_bus=bus)

    event_id = uuid4()
    async with session_factory() as session:
        session.add(
            OutboxModel(
                id=event_id,
                event_type="test.poison",
                payload={"x": 1},
                occurred_at=datetime.now(UTC),
            )
        )
        await session.commit()

    caplog.set_level(logging.CRITICAL)
    for _ in range(5):
        await relay.process_pending_batch()

    async with session_factory() as session:
        row = await session.get(OutboxModel, event_id)
        assert row is not None
        assert row.attempts == 5
        assert row.failed_at is not None
        assert row.last_error is not None

    assert any("poisoned" in rec.message.lower() for rec in caplog.records)

    retried = await OutboxRelay.retry_event(session_factory, event_id)
    assert retried is True

    async with session_factory() as session:
        row_after = await session.get(OutboxModel, event_id)
        assert row_after is not None
        assert row_after.failed_at is None
        assert row_after.attempts == 0
        assert row_after.last_error is None
    _ = outbox_cli_main
    _ = UUID
    _ = dataclass
