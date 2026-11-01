from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from src.modules.billing.domain.model.aggregates.credit_wallet import CreditWallet
from src.modules.billing.domain.model.value_objects.credit_transaction import (
    TransactionType,
)
from src.modules.billing.domain.repositories.credit_transaction_repository import (
    CreditTransactionRepository,
)
from src.modules.billing.domain.repositories.credit_wallet_repository import (
    CreditWalletRepository,
)
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.application.unit_of_work import UnitOfWork
from src.shared.domain.domain_error import DomainError

LIMA_TZ = ZoneInfo("America/Lima")


@dataclass(frozen=True, slots=True)
class DebitSearchCommand:
    user_id: UUID
    search_id: str


@dataclass(frozen=True, slots=True)
class DebitDTO:
    credits_charged: int
    credits_remaining: int


class DebitSearchHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        wallet_repo: CreditWalletRepository,
        tx_repo: CreditTransactionRepository,
    ) -> None:
        self._uow = uow
        self._wallet_repo = wallet_repo
        self._tx_repo = tx_repo

    async def handle(self, cmd: DebitSearchCommand) -> Result[DebitDTO]:
        now = datetime.now(UTC)
        today = now.astimezone(LIMA_TZ).date()

        async with self._uow:
            existing = await self._tx_repo.find(TransactionType.SEARCH_DEBIT, cmd.search_id)
            wallet = await self._wallet_repo.get_or_open_for_update(cmd.user_id, today=today)
            if existing is not None:
                view = wallet.view(today)
                return Result.success(
                    DebitDTO(
                        credits_charged=CreditWallet.SEARCH_COST,
                        credits_remaining=view.total_credits,
                    )
                )

            try:
                tx = wallet.debit(
                    amount=CreditWallet.SEARCH_COST,
                    today=today,
                    reference_id=cmd.search_id,
                    now=now,
                )
            except DomainError as exc:
                return Result.failure(ApplicationError(code=exc.code, message=exc.message))

            await self._wallet_repo.save(wallet)
            await self._tx_repo.add(cmd.user_id, tx)
            await self._uow.commit()
            remaining = wallet.free_credits + wallet.paid_credits

        return Result.success(
            DebitDTO(
                credits_charged=CreditWallet.SEARCH_COST,
                credits_remaining=remaining,
            )
        )
