from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from src.modules.iam.domain.repositories.refresh_token_repository import (
    RefreshTokenRepository,
)
from src.modules.iam.domain.repositories.user_repository import UserRepository
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.application.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class DeleteMyAccountCommand:
    user_id: UUID
    confirmation: str


class DeleteMyAccountHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        user_repo: UserRepository,
        refresh_repo: RefreshTokenRepository,
    ) -> None:
        self._uow = uow
        self._user_repo = user_repo
        self._refresh_repo = refresh_repo

    async def handle(self, cmd: DeleteMyAccountCommand) -> Result[None]:
        if cmd.confirmation != "ELIMINAR":
            return Result.failure(
                ApplicationError(
                    code="VALIDATION_ERROR",
                    message='La confirmación debe ser exactamente "ELIMINAR".',
                    details={
                        "invalid_params": [
                            {"name": "confirmation", "reason": "must equal ELIMINAR"}
                        ]
                    },
                )
            )

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
            user.delete(now)
            await self._user_repo.save(user)
            await self._refresh_repo.revoke_all_for_user(user.id.value, now)
            await self._uow.commit()

        return Result.success(None)
