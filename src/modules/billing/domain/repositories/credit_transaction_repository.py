from typing import Protocol
from uuid import UUID

from src.modules.billing.domain.model.value_objects.credit_transaction import (
    CreditTransaction,
    TransactionType,
)


class CreditTransactionRepository(Protocol):
    async def add(self, user_id: UUID, tx: CreditTransaction) -> None: ...

    async def find(
        self, tx_type: TransactionType, reference_id: str
    ) -> CreditTransaction | None: ...

    async def list_for_user(
        self, user_id: UUID, page: int, page_size: int
    ) -> tuple[list[CreditTransaction], int]: ...
