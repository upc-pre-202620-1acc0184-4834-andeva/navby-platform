from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.billing.domain.model.aggregates.credit_order import (
    CreditOrder,
    OrderStatus,
)
from src.modules.billing.domain.model.value_objects.credit_package import (
    CreditPackage,
    get_package_by_code,
)
from src.modules.billing.domain.repositories.credit_order_repository import (
    CreditOrderRepository,
)
from src.modules.billing.infrastructure.persistence.models import CreditOrderModel
from src.shared.infrastructure.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork


class SqlAlchemyCreditOrderRepository(CreditOrderRepository):
    def __init__(self, session_or_uow: AsyncSession | SqlAlchemyUnitOfWork) -> None:
        self._target = session_or_uow

    @property
    def _session(self) -> AsyncSession:
        if isinstance(self._target, SqlAlchemyUnitOfWork):
            return self._target.session
        return self._target

    @staticmethod
    def _to_domain(row: CreditOrderModel) -> CreditOrder:
        pkg = get_package_by_code(row.package_code) or CreditPackage(
            code=row.package_code,
            name=row.package_code,
            credits=row.credits,
            price_pen=Decimal(str(row.amount)),
            usd_reference=Decimal("0.00"),
        )
        return CreditOrder(
            id=row.id,
            user_id=row.user_id,
            package=pkg,
            amount=Decimal(str(row.amount)),
            currency=row.currency,
            status=OrderStatus(row.status),
            expires_at=row.expires_at,
            mp_preference_id=row.mp_preference_id,
            mp_payment_id=row.mp_payment_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def get(self, order_id: UUID) -> CreditOrder | None:
        row = await self._session.get(CreditOrderModel, order_id)
        return self._to_domain(row) if row is not None else None

    async def get_for_update(self, order_id: UUID) -> CreditOrder | None:
        stmt = select(CreditOrderModel).where(CreditOrderModel.id == order_id).with_for_update()
        res = await self._session.execute(stmt)
        row = res.scalar_one_or_none()
        return self._to_domain(row) if row is not None else None

    async def add(self, order: CreditOrder) -> None:
        row = CreditOrderModel(
            id=order.id,
            user_id=order.user_id,
            package_code=order.package.code,
            credits=order.package.credits,
            amount=order.amount,
            currency=order.currency,
            status=order.status.value,
            expires_at=order.expires_at,
            mp_preference_id=order.mp_preference_id,
            mp_payment_id=order.mp_payment_id,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )
        self._session.add(row)

    async def save(self, order: CreditOrder) -> None:
        row = await self._session.get(CreditOrderModel, order.id)
        if row is None:
            await self.add(order)
            return
        row.status = order.status.value
        row.mp_preference_id = order.mp_preference_id
        row.mp_payment_id = order.mp_payment_id
        row.updated_at = order.updated_at

    async def list_expired_pending(self, now: datetime) -> list[CreditOrder]:
        stmt = (
            select(CreditOrderModel)
            .where(
                CreditOrderModel.status == OrderStatus.PENDING.value,
                CreditOrderModel.expires_at < now,
            )
            .with_for_update(skip_locked=True)
        )
        res = await self._session.execute(stmt)
        return [self._to_domain(r) for r in res.scalars().all()]
