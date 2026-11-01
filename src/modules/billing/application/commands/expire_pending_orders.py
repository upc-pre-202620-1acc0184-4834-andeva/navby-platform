from datetime import UTC, datetime

from src.modules.billing.domain.repositories.credit_order_repository import (
    CreditOrderRepository,
)
from src.shared.application.unit_of_work import UnitOfWork


class ExpirePendingOrdersHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        order_repo: CreditOrderRepository,
    ) -> None:
        self._uow = uow
        self._order_repo = order_repo

    async def handle(self, now: datetime | None = None) -> int:
        ts = now or datetime.now(UTC)
        count = 0
        async with self._uow:
            expired_orders = await self._order_repo.list_expired_pending(ts)
            for order in expired_orders:
                if order.expire(ts):
                    await self._order_repo.save(order)
                    count += 1
            if count > 0:
                await self._uow.commit()
        return count
