from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.modules.iam.domain.repositories.user_repository import UserRepository
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.application.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class GetMyProfileQuery:
    user_id: UUID


@dataclass(frozen=True, slots=True)
class UserProfileDTO:
    user_id: UUID
    email: str
    full_name: str
    email_verified: bool
    has_password: bool
    has_google: bool
    created_at: datetime


class GetMyProfileHandler:
    def __init__(self, uow: UnitOfWork, user_repo: UserRepository) -> None:
        self._uow = uow
        self._user_repo = user_repo

    async def handle(self, query: GetMyProfileQuery) -> Result[UserProfileDTO]:
        async with self._uow:
            user = await self._user_repo.get_by_id(query.user_id)
            if user is None or user.deleted_at is not None:
                return Result.failure(
                    ApplicationError(
                        code="UNAUTHENTICATED",
                        message="La cuenta no existe o fue eliminada.",
                    )
                )
            return Result.success(
                UserProfileDTO(
                    user_id=user.id.value,
                    email=user.email.value,
                    full_name=user.full_name.value,
                    email_verified=user.email_verified,
                    has_password=user.password_hash is not None,
                    has_google=user.google_sub is not None,
                    created_at=user.created_at,
                )
            )
