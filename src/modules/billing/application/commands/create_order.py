from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from src.modules.billing.application.acl.ports.payment_gateway import PaymentGateway
from src.modules.billing.domain.model.aggregates.credit_order import CreditOrder
from src.modules.billing.domain.model.value_objects.credit_package import (
    get_package_by_code,
)
from src.modules.billing.domain.repositories.credit_order_repository import (
    CreditOrderRepository,
)
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.application.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class CreateOrderCommand:
    user_id: UUID
    package_code: str


@dataclass(frozen=True, slots=True)
class CreatedOrderDTO:
    order: CreditOrder
    checkout_url: str


class CreateOrderHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        order_repo: CreditOrderRepository,
        payment_gateway: PaymentGateway,
    ) -> None:
        self._uow = uow
        self._order_repo = order_repo
        self._payment_gateway = payment_gateway

    async def handle(self, cmd: CreateOrderCommand) -> Result[CreatedOrderDTO]:
        pkg = get_package_by_code(cmd.package_code)
        if pkg is None:
            return Result.failure(
                ApplicationError(
                    code="PACKAGE_NOT_FOUND",
                    message="El paquete de créditos solicitado no existe.",
                )
            )

        now = datetime.now(UTC)
        order = CreditOrder.create(user_id=cmd.user_id, package=pkg, now=now)
        try:
            pref_id, checkout_url = await self._payment_gateway.create_preference(order)
        except Exception:
            return Result.failure(
                ApplicationError(
                    code="PROVIDER_UNAVAILABLE",
                    message="No se pudo crear la preferencia de pago en Mercado Pago.",
                )
            )
        order.mp_preference_id = pref_id

        async with self._uow:
            await self._order_repo.add(order)
            await self._uow.commit()

        return Result.success(CreatedOrderDTO(order=order, checkout_url=checkout_url))
