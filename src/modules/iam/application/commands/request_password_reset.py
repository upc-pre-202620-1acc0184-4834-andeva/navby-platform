import hashlib
import logging
import secrets
from dataclasses import dataclass

from src.modules.iam.application.acl.ports.email_sender import EmailSender
from src.modules.iam.application.acl.ports.one_time_code_store import OneTimeCodeStore
from src.modules.iam.domain.model.value_objects.email import Email
from src.modules.iam.domain.repositories.user_repository import UserRepository
from src.shared.application.result import Result
from src.shared.application.unit_of_work import UnitOfWork
from src.shared.domain.domain_error import DomainError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RequestPasswordResetCommand:
    email: str
    webapp_url: str


class RequestPasswordResetHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        user_repo: UserRepository,
        otp_store: OneTimeCodeStore,
        email_sender: EmailSender,
    ) -> None:
        self._uow = uow
        self._user_repo = user_repo
        self._otp_store = otp_store
        self._email_sender = email_sender

    async def handle(self, cmd: RequestPasswordResetCommand) -> Result[None]:
        try:
            email_vo = Email(cmd.email)
        except DomainError:
            return Result.success(None)

        async with self._uow:
            user = await self._user_repo.get_by_email(email_vo.value)

        if user is None or user.deleted_at is not None:
            return Result.success(None)

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        await self._otp_store.save_reset(token_hash, user.id.value)

        base = cmd.webapp_url.rstrip("/")
        link = f"{base}/reset-password?token={raw_token}"
        try:
            await self._email_sender.send_password_reset(user.email.value, link)
        except Exception as exc:
            logger.error("Failed to send password reset email to %s: %s", user.id.value, exc)

        return Result.success(None)
