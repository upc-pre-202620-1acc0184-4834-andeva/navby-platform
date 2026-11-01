from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.iam.domain.model.aggregates.user import User
from src.modules.iam.domain.model.value_objects.email import Email
from src.modules.iam.domain.model.value_objects.full_name import FullName
from src.modules.iam.domain.model.value_objects.password_hash import PasswordHash
from src.modules.iam.domain.model.value_objects.user_id import UserId
from src.modules.iam.domain.repositories.user_repository import UserRepository
from src.modules.iam.infrastructure.persistence.models import UserModel
from src.shared.domain.integration_event import IntegrationEvent
from src.shared.infrastructure.outbox_model import OutboxModel
from src.shared.infrastructure.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session_or_uow: AsyncSession | SqlAlchemyUnitOfWork) -> None:
        self._target = session_or_uow

    @property
    def _session(self) -> AsyncSession:
        if isinstance(self._target, SqlAlchemyUnitOfWork):
            return self._target.session
        return self._target

    def _flush_events(self, user: User) -> None:
        for event in user.pull_events():
            if isinstance(event, IntegrationEvent):
                self._session.add(
                    OutboxModel(
                        id=event.event_id,
                        event_type=event.event_type,
                        payload=event.to_payload(),
                        occurred_at=event.occurred_at,
                    )
                )

    @staticmethod
    def _to_domain(row: UserModel) -> User:
        return User(
            id=UserId(row.id),
            email=Email(row.email),
            full_name=FullName(row.full_name),
            password_hash=(PasswordHash(row.password_hash) if row.password_hash else None),
            google_sub=row.google_sub,
            email_verified=row.email_verified,
            terms_version=row.terms_version,
            terms_accepted_at=row.terms_accepted_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
            deleted_at=row.deleted_at,
        )

    async def get_by_id(self, user_id: UUID) -> User | None:
        row = await self._session.get(UserModel, user_id)
        if row is None or row.deleted_at is not None:
            return None
        return self._to_domain(row)

    async def get_by_email(self, email: str) -> User | None:
        normalized = email.strip().lower()
        stmt = select(UserModel).where(
            func.lower(UserModel.email) == normalized,
            UserModel.deleted_at.is_(None),
        )
        res = await self._session.execute(stmt)
        row = res.scalar_one_or_none()
        return self._to_domain(row) if row is not None else None

    async def get_by_google_sub(self, google_sub: str) -> User | None:
        stmt = select(UserModel).where(
            UserModel.google_sub == google_sub,
            UserModel.deleted_at.is_(None),
        )
        res = await self._session.execute(stmt)
        row = res.scalar_one_or_none()
        return self._to_domain(row) if row is not None else None

    async def add(self, user: User) -> None:
        row = UserModel(
            id=user.id.value,
            email=user.email.value,
            full_name=user.full_name.value,
            password_hash=(user.password_hash.value if user.password_hash is not None else None),
            google_sub=user.google_sub,
            email_verified=user.email_verified,
            terms_version=user.terms_version,
            terms_accepted_at=user.terms_accepted_at,
            created_at=user.created_at,
            updated_at=user.updated_at,
            deleted_at=user.deleted_at,
        )
        self._session.add(row)
        self._flush_events(user)
        await self._session.flush()

    async def save(self, user: User) -> None:
        row = await self._session.get(UserModel, user.id.value)
        if row is None:
            await self.add(user)
            return
        row.email = user.email.value
        row.full_name = user.full_name.value
        row.password_hash = user.password_hash.value if user.password_hash is not None else None
        row.google_sub = user.google_sub
        row.email_verified = user.email_verified
        row.terms_version = user.terms_version
        row.terms_accepted_at = user.terms_accepted_at
        row.updated_at = user.updated_at
        row.deleted_at = user.deleted_at
        self._flush_events(user)
        await self._session.flush()
