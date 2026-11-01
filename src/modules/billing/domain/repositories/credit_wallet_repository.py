from datetime import date
from typing import Protocol
from uuid import UUID

from src.modules.billing.domain.model.aggregates.credit_wallet import CreditWallet


class CreditWalletRepository(Protocol):
    async def get(self, user_id: UUID) -> CreditWallet | None: ...

    async def get_for_update(self, user_id: UUID) -> CreditWallet | None: ...

    async def get_or_open_for_update(self, user_id: UUID, today: date) -> CreditWallet: ...

    async def insert_if_absent(self, wallet: CreditWallet) -> bool: ...

    async def save(self, wallet: CreditWallet) -> None: ...
