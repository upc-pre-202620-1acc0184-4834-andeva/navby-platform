from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.billing.domain.model.value_objects.credit_transaction import (
    CreditTransaction,
    TransactionType,
)
from src.modules.billing.domain.repositories.credit_transaction_repository import (
    CreditTransactionRepository,
)
from src.modules.billing.infrastructure.persistence.models import (
    CreditTransactionModel,
)
from src.shared.infrastructure.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork


class SqlAlchemyCreditTransactionRepository(CreditTransactionRepository):
    def __init__(self, session_or_uow: AsyncSession | SqlAlchemyUnitOfWork) -> None:
        self._target = session_or_uow

    @property
    def _session(self) -> AsyncSession:
        if isinstance(self._target, SqlAlchemyUnitOfWork):
            return self._target.session
        return self._target

    @staticmethod
    def _to_domain(row: CreditTransactionModel) -> CreditTransaction:
        return CreditTransaction(
            id=row.id,
            type=TransactionType(row.type),
            free_delta=row.free_delta,
            paid_delta=row.paid_delta,
            reference_id=row.reference_id,
            created_at=row.created_at,
        )

    async def add(self, user_id: UUID, tx: CreditTransaction) -> None:
        row = CreditTransactionModel(
            id=tx.id,
            user_id=user_id,
            type=tx.type.value,
            free_delta=tx.free_delta,
            paid_delta=tx.paid_delta,
            reference_id=tx.reference_id,
            created_at=tx.created_at,
        )
        self._session.add(row)

    async def find(self, tx_type: TransactionType, reference_id: str) -> CreditTransaction | None:
        stmt = select(CreditTransactionModel).where(
            CreditTransactionModel.type == tx_type.value,
            CreditTransactionModel.reference_id == reference_id,
        )
        res = await self._session.execute(stmt)
        row = res.scalar_one_or_none()
        return self._to_domain(row) if row is not None else None

    async def list_for_user(
        self, user_id: UUID, page: int, page_size: int
    ) -> tuple[list[CreditTransaction], int]:
        count_stmt = (
            select(func.count())
            .select_from(CreditTransactionModel)
            .where(CreditTransactionModel.user_id == user_id)
        )
        total = int((await self._session.execute(count_stmt)).scalar_one())

        offset = (page - 1) * page_size
        stmt = (
            select(CreditTransactionModel)
            .where(CreditTransactionModel.user_id == user_id)
            .order_by(
                CreditTransactionModel.created_at.desc(),
                CreditTransactionModel.id.desc(),
            )
            .offset(offset)
            .limit(page_size)
        )
        res = await self._session.execute(stmt)
        items = [self._to_domain(r) for r in res.scalars().all()]
        return items, total
