from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from src.modules.billing.domain.model.value_objects.credit_transaction import (
    CreditTransaction,
    TransactionType,
)
from src.shared.domain.aggregate_root import AggregateRoot
from src.shared.domain.domain_error import DomainError


@dataclass(frozen=True, slots=True)
class WalletView:
    free_credits: int
    paid_credits: int
    total_credits: int
    available_searches: int


class CreditWallet(AggregateRoot):
    DAILY_FREE_QUOTA = 10
    SEARCH_COST = 5

    def __init__(
        self,
        user_id: UUID,
        free_credits: int,
        free_credits_date: date,
        paid_credits: int,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__()
        self.user_id = user_id
        self.free_credits = free_credits
        self.free_credits_date = free_credits_date
        self.paid_credits = paid_credits
        self.updated_at = updated_at or datetime.now(UTC)

    @staticmethod
    def open(user_id: UUID, today: date, now: datetime | None = None) -> "CreditWallet":
        return CreditWallet(
            user_id=user_id,
            free_credits=CreditWallet.DAILY_FREE_QUOTA,
            free_credits_date=today,
            paid_credits=0,
            updated_at=now or datetime.now(UTC),
        )

    def view(self, today: date) -> WalletView:
        effective_free = (
            self.DAILY_FREE_QUOTA if self.free_credits_date < today else self.free_credits
        )
        total = effective_free + self.paid_credits
        return WalletView(
            free_credits=effective_free,
            paid_credits=self.paid_credits,
            total_credits=total,
            available_searches=total // self.SEARCH_COST,
        )

    def refresh_daily(self, today: date) -> None:
        if self.free_credits_date < today:
            self.free_credits = self.DAILY_FREE_QUOTA
            self.free_credits_date = today

    def debit(
        self,
        amount: int,
        today: date,
        reference_id: str | None = None,
        now: datetime | None = None,
    ) -> CreditTransaction:
        self.refresh_daily(today)
        total = self.free_credits + self.paid_credits
        if total < amount:
            raise DomainError(
                "INSUFFICIENT_CREDITS",
                "Saldo insuficiente para ejecutar la búsqueda.",
            )
        from_free = min(self.free_credits, amount)
        from_paid = amount - from_free
        self.free_credits -= from_free
        self.paid_credits -= from_paid
        ts = now or datetime.now(UTC)
        self.updated_at = ts
        return CreditTransaction(
            type=TransactionType.SEARCH_DEBIT,
            free_delta=-from_free,
            paid_delta=-from_paid,
            reference_id=reference_id,
            created_at=ts,
        )

    def refund(
        self,
        debit_tx: CreditTransaction,
        today: date,
        debit_date: date | None = None,
        now: datetime | None = None,
    ) -> CreditTransaction:
        self.refresh_daily(today)
        same_day = (debit_date == today) if debit_date is not None else True
        free_restore = -debit_tx.free_delta if same_day else 0
        if same_day:
            free_restore = min(free_restore, self.DAILY_FREE_QUOTA - self.free_credits)
        paid_restore = -debit_tx.paid_delta
        self.free_credits += free_restore
        self.paid_credits += paid_restore
        ts = now or datetime.now(UTC)
        self.updated_at = ts
        return CreditTransaction(
            type=TransactionType.SEARCH_REFUND,
            free_delta=free_restore,
            paid_delta=paid_restore,
            reference_id=debit_tx.reference_id,
            created_at=ts,
        )

    def add_paid(
        self,
        credits: int,
        reference_id: str | None = None,
        now: datetime | None = None,
    ) -> CreditTransaction:
        self.paid_credits += credits
        ts = now or datetime.now(UTC)
        self.updated_at = ts
        return CreditTransaction(
            type=TransactionType.PURCHASE,
            free_delta=0,
            paid_delta=credits,
            reference_id=reference_id,
            created_at=ts,
        )

    def remove_paid(
        self,
        credits: int,
        reference_id: str | None = None,
        now: datetime | None = None,
    ) -> CreditTransaction:
        removed = min(credits, self.paid_credits)
        self.paid_credits -= removed
        ts = now or datetime.now(UTC)
        self.updated_at = ts
        return CreditTransaction(
            type=TransactionType.PURCHASE_REVERSAL,
            free_delta=0,
            paid_delta=-removed,
            reference_id=reference_id,
            created_at=ts,
        )

    def forfeit(self, now: datetime | None = None) -> CreditTransaction:
        free_lost = self.free_credits
        paid_lost = self.paid_credits
        self.free_credits = 0
        self.paid_credits = 0
        ts = now or datetime.now(UTC)
        self.updated_at = ts
        return CreditTransaction(
            type=TransactionType.ACCOUNT_DELETION,
            free_delta=-free_lost,
            paid_delta=-paid_lost,
            reference_id=str(self.user_id),
            created_at=ts,
        )
