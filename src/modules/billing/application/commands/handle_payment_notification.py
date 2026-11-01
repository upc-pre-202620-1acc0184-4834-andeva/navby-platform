import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from src.modules.billing.application.acl.ports.payment_gateway import PaymentGateway
from src.modules.billing.domain.model.value_objects.credit_transaction import (
    TransactionType,
)
from src.modules.billing.domain.repositories.credit_order_repository import (
    CreditOrderRepository,
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

logger = logging.getLogger(__name__)
LIMA_TZ = ZoneInfo("America/Lima")


@dataclass(frozen=True, slots=True)
class HandlePaymentNotificationCommand:
    event_type: str
    data_id: str
    x_signature: str
    x_request_id: str


class HandlePaymentNotificationHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        order_repo: CreditOrderRepository,
        wallet_repo: CreditWalletRepository,
        tx_repo: CreditTransactionRepository,
        payment_gateway: PaymentGateway,
    ) -> None:
        self._uow = uow
        self._order_repo = order_repo
        self._wallet_repo = wallet_repo
        self._tx_repo = tx_repo
        self._payment_gateway = payment_gateway

    async def handle(self, cmd: HandlePaymentNotificationCommand) -> Result[None]:
        if cmd.event_type != "payment":
            return Result.success(None)

        if not self._payment_gateway.verify_signature(
            x_signature=cmd.x_signature,
            x_request_id=cmd.x_request_id,
            data_id=cmd.data_id,
        ):
            return Result.failure(
                ApplicationError(
                    code="INVALID_WEBHOOK_SIGNATURE",
                    message="Firma de webhook de Mercado Pago inválida o expirada.",
                )
            )

        payment = await self._payment_gateway.get_payment(cmd.data_id)
        if payment is None or not payment.external_reference:
            return Result.success(None)

        try:
            order_id = UUID(payment.external_reference)
        except ValueError:
            return Result.success(None)

        now = datetime.now(UTC)
        today = now.astimezone(LIMA_TZ).date()

        async with self._uow:
            order = await self._order_repo.get_for_update(order_id)
            if order is None:
                return Result.success(None)

            st = payment.status.lower()
            if st == "approved":
                try:
                    changed = order.approve(payment, now=now)
                except DomainError as exc:
                    if exc.code == "PAYMENT_MISMATCH":
                        logger.critical(
                            "PAYMENT_MISMATCH on order %s: %s",
                            order.id,
                            exc.message,
                        )
                        return Result.success(None)
                    raise

                if changed:
                    existing_tx = await self._tx_repo.find(TransactionType.PURCHASE, str(order.id))
                    if existing_tx is None:
                        wallet = await self._wallet_repo.get_or_open_for_update(
                            order.user_id, today=today
                        )
                        tx = wallet.add_paid(
                            credits=order.package.credits,
                            reference_id=str(order.id),
                            now=now,
                        )
                        await self._wallet_repo.save(wallet)
                        await self._tx_repo.add(order.user_id, tx)
                    await self._order_repo.save(order)
                    await self._uow.commit()

            elif st in {"rejected", "cancelled"}:
                if order.reject(payment.payment_id, now=now):
                    await self._order_repo.save(order)
                    await self._uow.commit()

            elif st in {"refunded", "charged_back"}:
                if order.reverse(payment.payment_id, now=now):
                    existing_rev = await self._tx_repo.find(
                        TransactionType.PURCHASE_REVERSAL, str(order.id)
                    )
                    if existing_rev is None:
                        wallet = await self._wallet_repo.get_or_open_for_update(
                            order.user_id, today=today
                        )
                        rev_tx = wallet.remove_paid(
                            credits=order.package.credits,
                            reference_id=str(order.id),
                            now=now,
                        )
                        await self._wallet_repo.save(wallet)
                        await self._tx_repo.add(order.user_id, rev_tx)
                    await self._order_repo.save(order)
                    await self._uow.commit()

        return Result.success(None)
