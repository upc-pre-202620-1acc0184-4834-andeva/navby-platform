import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from src.modules.iam.application.acl.ports.disposable_email_policy import (
    DisposableEmailPolicy,
)
from src.modules.iam.application.acl.ports.email_sender import EmailSender
from src.modules.iam.application.acl.ports.one_time_code_store import OneTimeCodeStore
from src.modules.iam.application.acl.ports.password_hasher import PasswordHasher
from src.modules.iam.domain.model.aggregates.user import User
from src.modules.iam.domain.model.value_objects.email import Email
from src.modules.iam.domain.model.value_objects.full_name import FullName
from src.modules.iam.domain.model.value_objects.plain_password import PlainPassword
from src.modules.iam.domain.repositories.user_repository import UserRepository
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.application.unit_of_work import UnitOfWork
from src.shared.domain.domain_error import DomainError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RegisterUserCommand:
    email: str
    password: str
    full_name: str
    accept_terms: bool
    terms_version: str


@dataclass(frozen=True, slots=True)
class RegisterUserDTO:
    user_id: UUID
    email: str
    email_verified: bool


class RegisterUserHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        user_repo: UserRepository,
        password_hasher: PasswordHasher,
        disposable_policy: DisposableEmailPolicy,
        otp_store: OneTimeCodeStore,
        email_sender: EmailSender,
    ) -> None:
        self._uow = uow
        self._user_repo = user_repo
        self._password_hasher = password_hasher
        self._disposable_policy = disposable_policy
        self._otp_store = otp_store
        self._email_sender = email_sender

    async def handle(self, cmd: RegisterUserCommand) -> Result[RegisterUserDTO]:
        if not cmd.accept_terms:
            return Result.failure(
                ApplicationError(
                    code="TERMS_NOT_ACCEPTED",
                    message="Debes aceptar los Términos de Servicio y la Política de Privacidad.",
                )
            )
        try:
            email_vo = Email(cmd.email)
            full_name_vo = FullName(cmd.full_name)
            plain_pw = PlainPassword(cmd.password)
        except DomainError as exc:
            return Result.failure(ApplicationError(code=exc.code, message=exc.message))

        if self._disposable_policy.is_disposable(email_vo.domain):
            return Result.failure(
                ApplicationError(
                    code="DISPOSABLE_EMAIL",
                    message="No se aceptan correos de dominios desechables.",
                )
            )

        async with self._uow:
            existing = await self._user_repo.get_by_email(email_vo.value)
            if existing is not None:
                return Result.failure(
                    ApplicationError(
                        code="EMAIL_ALREADY_REGISTERED",
                        message="El correo electrónico ya está registrado.",
                    )
                )

            pw_hash = self._password_hasher.hash(plain_pw)
            now = datetime.now(UTC)
            user = User.register_local(
                email=email_vo,
                full_name=full_name_vo,
                password_hash=pw_hash,
                terms_version=cmd.terms_version,
                now=now,
            )
            await self._user_repo.add(user)
            await self._uow.commit()

        otp_code = f"{secrets.randbelow(1_000_000):06d}"
        code_hash = hashlib.sha256(otp_code.encode()).hexdigest()
        await self._otp_store.save_otp(user.id.value, code_hash)

        try:
            await self._email_sender.send_verification_code(user.email.value, otp_code)
        except Exception as exc:
            logger.error("Failed to send verification email to %s: %s", user.id.value, exc)

        return Result.success(
            RegisterUserDTO(
                user_id=user.id.value,
                email=user.email.value,
                email_verified=user.email_verified,
            )
        )
