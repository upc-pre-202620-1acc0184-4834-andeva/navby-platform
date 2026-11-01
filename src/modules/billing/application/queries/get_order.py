from dataclasses import dataclass
from uuid import UUID

from src.modules.billing.domain.model.aggregates.credit_order import CreditOrder
from src.modules.billing.domain.repositories.credit_order_repository import (
    CreditOrderRepository,
)
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.application.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class GetOrderQuery:
    user_id: UUID
    order_id: UUID


class GetOrderHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        order_repo: CreditOrderRepository,
    ) -> None:
        self._uow = uow
        self._order_repo = order_repo

    async def handle(self, query: GetOrderQuery) -> Result[CreditOrder]:
        async with self._uow:
            order = await self._order_repo.get(query.order_id)
            if order is None or order.user_id != query.user_id:
                return Result.failure(
                    ApplicationError(
                        code="ORDER_NOT_FOUND",
                        message="La orden de compra no existe.",
                    )
                )
        return Result.success(order)
