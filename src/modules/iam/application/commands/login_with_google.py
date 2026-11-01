from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from src.modules.iam.application.acl.ports.disposable_email_policy import (
    DisposableEmailPolicy,
)
from src.modules.iam.application.acl.ports.google_identity_verifier import (
    GoogleIdentityVerifier,
)
from src.modules.iam.application.acl.ports.token_issuer import TokenIssuer
from src.modules.iam.application.commands.session_dto import SessionDTO, UserSummaryDTO
from src.modules.iam.domain.model.aggregates.user import User
from src.modules.iam.domain.model.entities.refresh_token import RefreshToken
from src.modules.iam.domain.model.value_objects.email import Email
from src.modules.iam.domain.model.value_objects.full_name import FullName
from src.modules.iam.domain.repositories.refresh_token_repository import (
    RefreshTokenRepository,
)
from src.modules.iam.domain.repositories.user_repository import UserRepository
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.application.unit_of_work import UnitOfWork
from src.shared.domain.domain_error import DomainError


@dataclass(frozen=True, slots=True)
class LoginWithGoogleCommand:
    id_token: str
    accept_terms: bool | None
    terms_version: str


class LoginWithGoogleHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        user_repo: UserRepository,
        refresh_repo: RefreshTokenRepository,
        google_verifier: GoogleIdentityVerifier,
        disposable_policy: DisposableEmailPolicy,
        token_issuer: TokenIssuer,
    ) -> None:
        self._uow = uow
        self._user_repo = user_repo
        self._refresh_repo = refresh_repo
        self._google_verifier = google_verifier
        self._disposable_policy = disposable_policy
        self._token_issuer = token_issuer

    async def handle(self, cmd: LoginWithGoogleCommand) -> Result[SessionDTO]:
        identity = await self._google_verifier.verify(cmd.id_token)
        if identity is None or not identity.email_verified:
            return Result.failure(
                ApplicationError(
                    code="INVALID_GOOGLE_TOKEN",
                    message="El token de Google es inválido o expiró.",
                )
            )

        try:
            email_vo = Email(identity.email)
            full_name_vo = FullName(identity.name or email_vo.value.split("@")[0])
        except DomainError as exc:
            return Result.failure(ApplicationError(code=exc.code, message=exc.message))

        now = datetime.now(UTC)
        async with self._uow:
            user = await self._user_repo.get_by_google_sub(identity.sub)
            if user is not None:
                if user.deleted_at is not None:
                    return Result.failure(
                        ApplicationError(
                            code="INVALID_GOOGLE_TOKEN",
                            message="La cuenta ha sido eliminada.",
                        )
                    )
            else:
                user_by_email = await self._user_repo.get_by_email(email_vo.value)
                if user_by_email is not None:
                    if user_by_email.deleted_at is not None:
                        return Result.failure(
                            ApplicationError(
                                code="INVALID_GOOGLE_TOKEN",
                                message="La cuenta ha sido eliminada.",
                            )
                        )
                    user_by_email.link_google(identity.sub, now=now)
                    await self._user_repo.save(user_by_email)
                    user = user_by_email
                else:
                    if not cmd.accept_terms:
                        return Result.failure(
                            ApplicationError(
                                code="TERMS_NOT_ACCEPTED",
                                message=(
                                    "Debes aceptar los Términos de Servicio "
                                    "y la Política de Privacidad."
                                ),
                            )
                        )
                    if self._disposable_policy.is_disposable(email_vo.domain):
                        return Result.failure(
                            ApplicationError(
                                code="DISPOSABLE_EMAIL",
                                message="No se aceptan correos de dominios desechables.",
                            )
                        )
                    user = User.register_google(
                        email=email_vo,
                        full_name=full_name_vo,
                        google_sub=identity.sub,
                        terms_version=cmd.terms_version,
                        now=now,
                    )
                    await self._user_repo.add(user)

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
