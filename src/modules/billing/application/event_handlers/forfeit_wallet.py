from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.billing.domain.model.value_objects.credit_transaction import (
    TransactionType,
)
from src.modules.billing.infrastructure.persistence.sqlalchemy_credit_transaction_repository import (  # noqa: E501
    SqlAlchemyCreditTransactionRepository,
)
from src.modules.billing.infrastructure.persistence.sqlalchemy_credit_wallet_repository import (
    SqlAlchemyCreditWalletRepository,
)
from src.modules.iam.domain.model.events.user_deleted import UserDeleted
from src.shared.domain.integration_event import IntegrationEvent


class ForfeitWalletHandler:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def handle(self, event: IntegrationEvent) -> None:
        if isinstance(event, UserDeleted):
            user_id = event.user_id
        else:
            user_id = UUID(str(event.to_payload()["user_id"]))

        now = datetime.now(UTC)
        async with self._session_factory() as session:
            wallet_repo = SqlAlchemyCreditWalletRepository(session)
            tx_repo = SqlAlchemyCreditTransactionRepository(session)

            existing_tx = await tx_repo.find(TransactionType.ACCOUNT_DELETION, str(user_id))
            if existing_tx is not None:
                return

            wallet = await wallet_repo.get_for_update(user_id)
            if wallet is None:
                return

            tx = wallet.forfeit(now=now)
            await wallet_repo.save(wallet)
            await tx_repo.add(user_id, tx)
            await session.commit()
