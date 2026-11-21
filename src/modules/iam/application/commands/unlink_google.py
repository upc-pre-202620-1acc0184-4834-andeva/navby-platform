from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from src.modules.iam.domain.repositories.user_repository import UserRepository
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.application.unit_of_work import UnitOfWork
from src.shared.domain.domain_error import DomainError


@dataclass(frozen=True, slots=True)
class UnlinkGoogleCommand:
    user_id: UUID


class UnlinkGoogleHandler:
    """Desvincula Google solo si la cuenta conserva la contraseña como forma de entrar."""

    def __init__(self, uow: UnitOfWork, user_repo: UserRepository) -> None:
        self._uow = uow
        self._user_repo = user_repo

    async def handle(self, cmd: UnlinkGoogleCommand) -> Result[None]:
        now = datetime.now(UTC)
        async with self._uow:
            user = await self._user_repo.get_by_id(cmd.user_id)
            if user is None or user.deleted_at is not None:
                return Result.failure(
                    ApplicationError(
                        code="UNAUTHENTICATED",
                        message="Usuario no encontrado o ya eliminado.",
                    )
                )
            try:
                user.unlink_google(now)
            except DomainError as exc:
                return Result.failure(ApplicationError(code=exc.code, message=exc.message))
            await self._user_repo.save(user)
            await self._uow.commit()

        return Result.success(None)
