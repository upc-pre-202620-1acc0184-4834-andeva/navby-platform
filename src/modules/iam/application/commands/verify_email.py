from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from src.modules.iam.application.acl.ports.one_time_code_store import (
    OneTimeCodeStore,
    OtpCheck,
)
from src.modules.iam.application.acl.ports.token_issuer import TokenIssuer
from src.modules.iam.application.commands.session_dto import SessionDTO, UserSummaryDTO
from src.modules.iam.domain.model.entities.refresh_token import RefreshToken
from src.modules.iam.domain.model.value_objects.email import Email
from src.modules.iam.domain.repositories.refresh_token_repository import (
    RefreshTokenRepository,
)
from src.modules.iam.domain.repositories.user_repository import UserRepository
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.application.unit_of_work import UnitOfWork
from src.shared.domain.domain_error import DomainError


@dataclass(frozen=True, slots=True)
class VerifyEmailCommand:
    email: str
    code: str


class VerifyEmailHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        user_repo: UserRepository,
        refresh_repo: RefreshTokenRepository,
        otp_store: OneTimeCodeStore,
        token_issuer: TokenIssuer,
    ) -> None:
        self._uow = uow
        self._user_repo = user_repo
        self._refresh_repo = refresh_repo
        self._otp_store = otp_store
        self._token_issuer = token_issuer

    async def handle(self, cmd: VerifyEmailCommand) -> Result[SessionDTO]:
        try:
            email_vo = Email(cmd.email)
        except DomainError:
            return Result.failure(
                ApplicationError(code="INVALID_OTP", message="Código inválido o expirado.")
            )

        async with self._uow:
            user = await self._user_repo.get_by_email(email_vo.value)
            if user is None or user.email_verified or user.deleted_at is not None:
                return Result.failure(
                    ApplicationError(code="INVALID_OTP", message="Código inválido o expirado.")
                )

            otp_status = await self._otp_store.check_otp(user.id.value, cmd.code.strip())
            if otp_status == OtpCheck.EXHAUSTED:
                return Result.failure(
                    ApplicationError(
                        code="OTP_ATTEMPTS_EXCEEDED",
                        message="Se superó el máximo de 5 intentos. Solicita un código nuevo.",
                    )
                )
            if otp_status != OtpCheck.VALID:
                return Result.failure(
                    ApplicationError(code="INVALID_OTP", message="Código inválido o expirado.")
                )

            now = datetime.now(UTC)
            user.verify_email(now)
            await self._user_repo.save(user)

            raw_refresh, refresh_hash = self._token_issuer.new_refresh()
            rt = RefreshToken(
                id=uuid4(),
                user_id=user.id.value,
                token_hash=refresh_hash,
                expires_at=now + timedelta(days=7),
                created_at=now,
            )
            await self._refresh_repo.add(rt)
            await self._uow.commit()

        access_token = self._token_issuer.issue_access(user)
        return Result.success(
            SessionDTO(
                access_token=access_token,
                refresh_token=raw_refresh,
                expires_in=900,
                user=UserSummaryDTO(
                    user_id=user.id.value,
                    email=user.email.value,
                    full_name=user.full_name.value,
                    email_verified=user.email_verified,
                ),
            )
        )
