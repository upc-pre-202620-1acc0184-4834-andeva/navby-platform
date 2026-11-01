from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from src.modules.billing.domain.model.events.order_approved import OrderApproved
from src.modules.billing.domain.model.events.order_reversed import OrderReversed
from src.modules.billing.domain.model.value_objects.credit_package import CreditPackage
from src.modules.billing.domain.model.value_objects.payment_info import PaymentInfo
from src.shared.domain.aggregate_root import AggregateRoot
from src.shared.domain.domain_error import DomainError


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REVERSED = "REVERSED"


class CreditOrder(AggregateRoot):
    def __init__(
        self,
        id: UUID,
        user_id: UUID,
        package: CreditPackage,
        amount: Decimal,
        currency: str,
        status: OrderStatus,
        expires_at: datetime,
        mp_preference_id: str,
        created_at: datetime,
        updated_at: datetime,
        mp_payment_id: str | None = None,
    ) -> None:
        super().__init__()
        self.id = id
        self.user_id = user_id
        self.package = package
        self.amount = amount
        self.currency = currency
        self.status = status
        self.expires_at = expires_at
        self.mp_preference_id = mp_preference_id
        self.mp_payment_id = mp_payment_id
        self.created_at = created_at
        self.updated_at = updated_at

    @staticmethod
    def create(
        user_id: UUID,
        package: CreditPackage,
        mp_preference_id: str = "",
        order_id: UUID | None = None,
        now: datetime | None = None,
    ) -> "CreditOrder":
        ts = now or datetime.now(UTC)
        return CreditOrder(
            id=order_id or uuid4(),
            user_id=user_id,
            package=package,
            amount=package.price_pen,
            currency="PEN",
            status=OrderStatus.PENDING,
            expires_at=ts + timedelta(hours=24),
            mp_preference_id=mp_preference_id,
            mp_payment_id=None,
            created_at=ts,
            updated_at=ts,
        )

    def approve(self, payment: PaymentInfo, now: datetime | None = None) -> bool:
        if self.status != OrderStatus.PENDING:
            return False
        if payment.amount != self.amount or payment.currency.upper() != "PEN":
            raise DomainError(
                "PAYMENT_MISMATCH",
                f"Monto o moneda no coinciden para la orden {self.id}: "
                f"esperado {self.amount} PEN, recibido {payment.amount} {payment.currency}.",
            )
        ts = now or datetime.now(UTC)
        self.status = OrderStatus.APPROVED
        self.mp_payment_id = payment.payment_id
        self.updated_at = ts
        self.record_event(
            OrderApproved(
                event_id=uuid4(),
                occurred_at=ts,
                order_id=self.id,
                user_id=self.user_id,
                credits=self.package.credits,
                payment_id=payment.payment_id,
            )
        )
        return True

    def reject(self, payment_id: str, now: datetime | None = None) -> bool:
        if self.status != OrderStatus.PENDING:
            return False
        self.status = OrderStatus.REJECTED
        self.mp_payment_id = payment_id
        self.updated_at = now or datetime.now(UTC)
        return True

    def expire(self, now: datetime) -> bool:
        if self.status != OrderStatus.PENDING or now <= self.expires_at:
            return False
        self.status = OrderStatus.EXPIRED
        self.updated_at = now
        return True

    def reverse(self, payment_id: str, now: datetime | None = None) -> bool:
        if self.status != OrderStatus.APPROVED:
            return False
        ts = now or datetime.now(UTC)
        self.status = OrderStatus.REVERSED
        self.mp_payment_id = payment_id
        self.updated_at = ts
        self.record_event(
            OrderReversed(
                event_id=uuid4(),
                occurred_at=ts,
                order_id=self.id,
                user_id=self.user_id,
                credits=self.package.credits,
                payment_id=payment_id,
            )
        )
        return True
