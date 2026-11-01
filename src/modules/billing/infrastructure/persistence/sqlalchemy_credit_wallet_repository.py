from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.billing.domain.model.aggregates.credit_wallet import CreditWallet
from src.modules.billing.domain.repositories.credit_wallet_repository import (
    CreditWalletRepository,
)
from src.modules.billing.infrastructure.persistence.models import CreditWalletModel
from src.shared.infrastructure.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork


class SqlAlchemyCreditWalletRepository(CreditWalletRepository):
    def __init__(self, session_or_uow: AsyncSession | SqlAlchemyUnitOfWork) -> None:
        self._target = session_or_uow

    @property
    def _session(self) -> AsyncSession:
        if isinstance(self._target, SqlAlchemyUnitOfWork):
            return self._target.session
        return self._target

    @staticmethod
    def _to_domain(row: CreditWalletModel) -> CreditWallet:
        return CreditWallet(
            user_id=row.user_id,
            free_credits=row.free_credits,
            free_credits_date=row.free_credits_date,
            paid_credits=row.paid_credits,
            updated_at=row.updated_at,
        )

    async def get(self, user_id: UUID) -> CreditWallet | None:
        row = await self._session.get(CreditWalletModel, user_id)
        return self._to_domain(row) if row is not None else None

    async def get_for_update(self, user_id: UUID) -> CreditWallet | None:
        stmt = (
            select(CreditWalletModel).where(CreditWalletModel.user_id == user_id).with_for_update()
        )
        res = await self._session.execute(stmt)
        row = res.scalar_one_or_none()
        return self._to_domain(row) if row is not None else None

    async def insert_if_absent(self, wallet: CreditWallet) -> bool:
        stmt = (
            pg_insert(CreditWalletModel)
            .values(
                user_id=wallet.user_id,
                free_credits=wallet.free_credits,
                free_credits_date=wallet.free_credits_date,
                paid_credits=wallet.paid_credits,
                updated_at=wallet.updated_at,
            )
            .on_conflict_do_nothing(index_elements=["user_id"])
            .returning(CreditWalletModel.user_id)
        )
        res = await self._session.execute(stmt)
        return res.first() is not None

    async def get_or_open_for_update(self, user_id: UUID, today: date) -> CreditWallet:
        now = datetime.now(UTC)
        await self.insert_if_absent(CreditWallet.open(user_id=user_id, today=today, now=now))
        wallet = await self.get_for_update(user_id)
        if wallet is None:
            raise RuntimeError(f"Failed to lock credit wallet for user {user_id}")
        return wallet

    async def save(self, wallet: CreditWallet) -> None:
        row = await self._session.get(CreditWalletModel, wallet.user_id)
        if row is None:
            row = CreditWalletModel(
                user_id=wallet.user_id,
                free_credits=wallet.free_credits,
                free_credits_date=wallet.free_credits_date,
                paid_credits=wallet.paid_credits,
                updated_at=wallet.updated_at,
            )
            self._session.add(row)
            return
        row.free_credits = wallet.free_credits
        row.free_credits_date = wallet.free_credits_date
        row.paid_credits = wallet.paid_credits
        row.updated_at = wallet.updated_at
