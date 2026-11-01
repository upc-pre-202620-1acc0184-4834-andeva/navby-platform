from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.billing.application.commands.debit_search import (
    DebitDTO,
    DebitSearchCommand,
    DebitSearchHandler,
)
from src.modules.billing.application.commands.refund_search import (
    RefundSearchCommand,
    RefundSearchHandler,
)
from src.modules.billing.application.queries.get_wallet import (
    GetWalletHandler,
    GetWalletQuery,
)
from src.modules.billing.infrastructure.persistence.sqlalchemy_credit_transaction_repository import (  # noqa: E501
    SqlAlchemyCreditTransactionRepository,
)
from src.modules.billing.infrastructure.persistence.sqlalchemy_credit_wallet_repository import (
    SqlAlchemyCreditWalletRepository,
)
from src.shared.application.result import Result
from src.shared.infrastructure.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork


class BillingFacade:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def debit_search(self, user_id: UUID, search_id: str) -> Result[DebitDTO]:
        uow = SqlAlchemyUnitOfWork(self._session_factory)
        handler = DebitSearchHandler(
            uow=uow,
            wallet_repo=SqlAlchemyCreditWalletRepository(uow),
            tx_repo=SqlAlchemyCreditTransactionRepository(uow),
        )
        return await handler.handle(DebitSearchCommand(user_id=user_id, search_id=search_id))

    async def refund_search(self, user_id: UUID, search_id: str) -> Result[int]:
        uow = SqlAlchemyUnitOfWork(self._session_factory)
        handler = RefundSearchHandler(
            uow=uow,
            wallet_repo=SqlAlchemyCreditWalletRepository(uow),
            tx_repo=SqlAlchemyCreditTransactionRepository(uow),
        )
        return await handler.handle(RefundSearchCommand(user_id=user_id, search_id=search_id))

    async def get_total_credits(self, user_id: UUID) -> int:
        uow = SqlAlchemyUnitOfWork(self._session_factory)
        handler = GetWalletHandler(
            uow=uow,
            wallet_repo=SqlAlchemyCreditWalletRepository(uow),
        )
        res = await handler.handle(GetWalletQuery(user_id=user_id))
        return res.value.total_credits
