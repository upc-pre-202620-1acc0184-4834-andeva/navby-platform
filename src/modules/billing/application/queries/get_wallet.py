from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from src.modules.billing.domain.model.aggregates.credit_wallet import CreditWallet
from src.modules.billing.domain.repositories.credit_wallet_repository import (
    CreditWalletRepository,
)
from src.shared.application.result import Result
from src.shared.application.unit_of_work import UnitOfWork

LIMA_TZ = ZoneInfo("America/Lima")


@dataclass(frozen=True, slots=True)
class GetWalletQuery:
    user_id: UUID


@dataclass(frozen=True, slots=True)
class WalletBalanceDTO:
    free_credits: int
    paid_credits: int
    total_credits: int
    searches_available: int
    free_credits_reset_at: datetime


class GetWalletHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        wallet_repo: CreditWalletRepository,
    ) -> None:
        self._uow = uow
        self._wallet_repo = wallet_repo

    async def handle(self, query: GetWalletQuery) -> Result[WalletBalanceDTO]:
        now_utc = datetime.now(UTC)
        now_lima = now_utc.astimezone(LIMA_TZ)
        today_lima = now_lima.date()
        next_midnight_lima = datetime.combine(
            today_lima + timedelta(days=1),
            time(0, 0, 0),
            tzinfo=LIMA_TZ,
        )
        reset_at_utc = next_midnight_lima.astimezone(UTC)

        async with self._uow:
            wallet = await self._wallet_repo.get(query.user_id)
            if wallet is None:
                wallet = CreditWallet.open(
                    user_id=query.user_id,
                    today=today_lima,
                    now=now_utc,
                )
            view = wallet.view(today_lima)

        return Result.success(
            WalletBalanceDTO(
                free_credits=view.free_credits,
                paid_credits=view.paid_credits,
                total_credits=view.total_credits,
                searches_available=view.available_searches,
                free_credits_reset_at=reset_at_utc,
            )
        )
