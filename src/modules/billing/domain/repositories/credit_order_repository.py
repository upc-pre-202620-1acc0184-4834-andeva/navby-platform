from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.modules.billing.domain.model.aggregates.credit_order import CreditOrder


class CreditOrderRepository(Protocol):
    async def get(self, order_id: UUID) -> CreditOrder | None: ...

    async def get_for_update(self, order_id: UUID) -> CreditOrder | None: ...

    async def add(self, order: CreditOrder) -> None: ...

    async def save(self, order: CreditOrder) -> None: ...

    async def list_expired_pending(self, now: datetime) -> list[CreditOrder]: ...
