from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.billing.domain.model.aggregates.credit_wallet import CreditWallet
from src.modules.billing.infrastructure.persistence.sqlalchemy_credit_wallet_repository import (
    SqlAlchemyCreditWalletRepository,
)
from src.modules.iam.domain.model.events.user_verified import UserVerified
from src.shared.domain.integration_event import IntegrationEvent

LIMA_TZ = ZoneInfo("America/Lima")


class OpenWalletHandler:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def handle(self, event: IntegrationEvent) -> None:
        if isinstance(event, UserVerified):
            user_id = event.user_id
        else:
            from uuid import UUID

            user_id = UUID(str(event.to_payload()["user_id"]))

        now = datetime.now(UTC)
        today = now.astimezone(LIMA_TZ).date()
        async with self._session_factory() as session:
            repo = SqlAlchemyCreditWalletRepository(session)
            await repo.insert_if_absent(CreditWallet.open(user_id=user_id, today=today, now=now))
            await session.commit()
