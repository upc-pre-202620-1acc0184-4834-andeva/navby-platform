from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from src.modules.billing.domain.model.value_objects.credit_transaction import (
    TransactionType,
)
from src.modules.billing.domain.repositories.credit_transaction_repository import (
    CreditTransactionRepository,
)
from src.modules.billing.domain.repositories.credit_wallet_repository import (
    CreditWalletRepository,
)
from src.shared.application.result import Result
from src.shared.application.unit_of_work import UnitOfWork

LIMA_TZ = ZoneInfo("America/Lima")


@dataclass(frozen=True, slots=True)
class RefundSearchCommand:
    user_id: UUID
    search_id: str


class RefundSearchHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        wallet_repo: CreditWalletRepository,
        tx_repo: CreditTransactionRepository,
    ) -> None:
        self._uow = uow
        self._wallet_repo = wallet_repo
        self._tx_repo = tx_repo

    async def handle(self, cmd: RefundSearchCommand) -> Result[int]:
        now = datetime.now(UTC)
        today = now.astimezone(LIMA_TZ).date()

        async with self._uow:
            existing_refund = await self._tx_repo.find(TransactionType.SEARCH_REFUND, cmd.search_id)
            wallet = await self._wallet_repo.get_or_open_for_update(cmd.user_id, today=today)
            if existing_refund is not None:
                return Result.success(wallet.view(today).total_credits)

            debit_tx = await self._tx_repo.find(TransactionType.SEARCH_DEBIT, cmd.search_id)
            if debit_tx is None:
                return Result.success(wallet.view(today).total_credits)

            debit_date = debit_tx.created_at.astimezone(LIMA_TZ).date()
            refund_tx = wallet.refund(
                debit_tx=debit_tx,
                today=today,
                debit_date=debit_date,
                now=now,
            )
            await self._wallet_repo.save(wallet)
            await self._tx_repo.add(cmd.user_id, refund_tx)
            await self._uow.commit()
            remaining = wallet.free_credits + wallet.paid_credits

        return Result.success(remaining)
