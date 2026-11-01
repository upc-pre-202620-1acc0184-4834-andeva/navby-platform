import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from src.modules.iam.application.acl.ports.one_time_code_store import OneTimeCodeStore
from src.modules.iam.application.acl.ports.password_hasher import PasswordHasher
from src.modules.iam.domain.model.value_objects.plain_password import PlainPassword
from src.modules.iam.domain.repositories.refresh_token_repository import (
    RefreshTokenRepository,
)
from src.modules.iam.domain.repositories.user_repository import UserRepository
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.application.unit_of_work import UnitOfWork
from src.shared.domain.domain_error import DomainError


@dataclass(frozen=True, slots=True)
class ResetPasswordCommand:
    token: str
    new_password: str


class ResetPasswordHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        user_repo: UserRepository,
        refresh_repo: RefreshTokenRepository,
        otp_store: OneTimeCodeStore,
        password_hasher: PasswordHasher,
    ) -> None:
        self._uow = uow
        self._user_repo = user_repo
        self._refresh_repo = refresh_repo
        self._otp_store = otp_store
        self._password_hasher = password_hasher

    async def handle(self, cmd: ResetPasswordCommand) -> Result[None]:
        try:
            plain_pw = PlainPassword(cmd.new_password)
        except DomainError as exc:
            return Result.failure(ApplicationError(code=exc.code, message=exc.message))

        raw_token = cmd.token.strip()
        if not raw_token:
            return Result.failure(
                ApplicationError(
                    code="INVALID_RESET_TOKEN",
                    message="El token de recuperación es inválido o expiró.",
                )
            )

        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        user_id = await self._otp_store.consume_reset(token_hash)
        if user_id is None:
            return Result.failure(
                ApplicationError(
                    code="INVALID_RESET_TOKEN",
                    message="El token de recuperación es inválido o expiró.",
                )
            )

        now = datetime.now(UTC)
        async with self._uow:
            user = await self._user_repo.get_by_id(user_id)
            if user is None or user.deleted_at is not None:
                return Result.failure(
                    ApplicationError(
                        code="INVALID_RESET_TOKEN",
                        message="El token de recuperación es inválido o expiró.",
                    )
                )
            pw_hash = self._password_hasher.hash(plain_pw)
            user.change_password(pw_hash, now=now)
            await self._user_repo.save(user)
            await self._refresh_repo.revoke_all_for_user(user.id.value, now)
            await self._uow.commit()

        return Result.success(None)
