from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.iam.domain.model.entities.refresh_token import RefreshToken
from src.modules.iam.domain.repositories.refresh_token_repository import (
    RefreshTokenRepository,
)
from src.modules.iam.infrastructure.persistence.models import RefreshTokenModel
from src.shared.infrastructure.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork


class SqlAlchemyRefreshTokenRepository(RefreshTokenRepository):
    def __init__(self, session_or_uow: AsyncSession | SqlAlchemyUnitOfWork) -> None:
        self._target = session_or_uow

    @property
    def _session(self) -> AsyncSession:
        if isinstance(self._target, SqlAlchemyUnitOfWork):
            return self._target.session
        return self._target

    @staticmethod
    def _to_domain(row: RefreshTokenModel) -> RefreshToken:
        return RefreshToken(
            id=row.id,
            user_id=row.user_id,
            token_hash=row.token_hash,
            expires_at=row.expires_at,
            created_at=row.created_at,
            revoked_at=row.revoked_at,
            replaced_by_hash=row.replaced_by_hash,
        )

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        res = await self._session.execute(stmt)
        row = res.scalar_one_or_none()
        return self._to_domain(row) if row is not None else None

    async def add(self, token: RefreshToken) -> None:
        row = RefreshTokenModel(
            id=token.id,
            user_id=token.user_id,
            token_hash=token.token_hash,
            expires_at=token.expires_at,
            revoked_at=token.revoked_at,
            replaced_by_hash=token.replaced_by_hash,
            created_at=token.created_at,
        )
        self._session.add(row)

    async def save(self, token: RefreshToken) -> None:
        row = await self._session.get(RefreshTokenModel, token.id)
        if row is None:
            await self.add(token)
            return
        row.revoked_at = token.revoked_at
        row.replaced_by_hash = token.replaced_by_hash

    async def revoke_all_for_user(self, user_id: UUID, now: datetime) -> None:
        stmt = (
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.user_id == user_id,
                RefreshTokenModel.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await self._session.execute(stmt)

    async def delete_expired(self, before: datetime) -> int:
        stmt = (
            delete(RefreshTokenModel)
            .where(
                (RefreshTokenModel.expires_at < before) | (RefreshTokenModel.revoked_at < before)
            )
            .returning(RefreshTokenModel.id)
        )
        res = await self._session.execute(stmt)
        return len(res.all())
