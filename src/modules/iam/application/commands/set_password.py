from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from src.modules.iam.application.acl.ports.password_hasher import PasswordHasher
from src.modules.iam.application.acl.ports.token_issuer import TokenIssuer
from src.modules.iam.domain.model.entities.refresh_token import RefreshToken
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
class SetPasswordCommand:
    user_id: UUID
    new_password: str
    # Obligatoria solo si la cuenta ya tiene contraseña; una cuenta solo-Google no la tiene.
    current_password: str | None = None


class SetPasswordHandler:
    """Crea la contraseña de una cuenta solo-Google o cambia la existente.

    Cierra todas las sesiones y abre una nueva para quien hizo el cambio: devuelve su refresh
    token en claro para que la interfaz REST lo fije en la cookie. Las demás sesiones pierden
    el acceso en cuanto vence su access token (15 min).
    """

    def __init__(
        self,
        uow: UnitOfWork,
        user_repo: UserRepository,
        refresh_repo: RefreshTokenRepository,
        password_hasher: PasswordHasher,
        token_issuer: TokenIssuer,
    ) -> None:
        self._uow = uow
        self._user_repo = user_repo
        self._refresh_repo = refresh_repo
        self._password_hasher = password_hasher
        self._token_issuer = token_issuer

    async def handle(self, cmd: SetPasswordCommand) -> Result[str]:
        try:
            plain_pw = PlainPassword(cmd.new_password)
        except DomainError as exc:
            return Result.failure(ApplicationError(code=exc.code, message=exc.message))

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

            if user.password_hash is not None:
                if not cmd.current_password:
                    return Result.failure(
                        ApplicationError(
                            code="VALIDATION_ERROR",
                            message="Indica tu contraseña actual.",
                            details={
                                "invalid_params": [
                                    {"name": "current_password", "reason": "required"}
                                ]
                            },
                        )
                    )
                if not self._password_hasher.verify(cmd.current_password, user.password_hash):
                    return Result.failure(
                        ApplicationError(
                            code="INVALID_CURRENT_PASSWORD",
                            message="La contraseña actual no es correcta.",
                        )
                    )

            user.change_password(self._password_hasher.hash(plain_pw), now=now)
            await self._user_repo.save(user)

            await self._refresh_repo.revoke_all_for_user(user.id.value, now)
            raw_refresh, refresh_hash = self._token_issuer.new_refresh()
            await self._refresh_repo.add(
                RefreshToken(
                    id=uuid4(),
                    user_id=user.id.value,
                    token_hash=refresh_hash,
                    expires_at=now + timedelta(days=7),
                    created_at=now,
                )
            )
            await self._uow.commit()

        return Result.success(raw_refresh)
