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
class ResendVerificationCommand:
    email: str


class ResendVerificationHandler:
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

    async def handle(self, cmd: ResendVerificationCommand) -> Result[None]:
        try:
            email_vo = Email(cmd.email)
        except DomainError:
            return Result.success(None)

        email_hash = hashlib.sha256(email_vo.value.encode()).hexdigest()
        if not await self._otp_store.can_resend_otp(email_hash):
            return Result.success(None)

        async with self._uow:
            user = await self._user_repo.get_by_email(email_vo.value)

        if user is None or user.email_verified or user.deleted_at is not None:
            return Result.success(None)

        otp_code = f"{secrets.randbelow(1_000_000):06d}"
        code_hash = hashlib.sha256(otp_code.encode()).hexdigest()
        await self._otp_store.save_otp(user.id.value, code_hash)
        await self._otp_store.mark_resend_otp(email_hash)

        try:
            await self._email_sender.send_verification_code(user.email.value, otp_code)
        except Exception as exc:
            logger.error("Failed to resend verification email to %s: %s", user.id.value, exc)

        return Result.success(None)
