from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from src.modules.iam.application.acl.ports.token_issuer import TokenIssuer
from src.modules.iam.application.commands.session_dto import SessionDTO, UserSummaryDTO
from src.modules.iam.domain.model.entities.refresh_token import RefreshToken
from src.modules.iam.domain.repositories.refresh_token_repository import (
    RefreshTokenRepository,
)
from src.modules.iam.domain.repositories.user_repository import UserRepository
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.application.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class RefreshSessionCommand:
    refresh_token: str | None


class RefreshSessionHandler:
    TAB_RACE_WINDOW_SECONDS = 30.0

    def __init__(
        self,
        uow: UnitOfWork,
        user_repo: UserRepository,
        refresh_repo: RefreshTokenRepository,
        token_issuer: TokenIssuer,
    ) -> None:
        self._uow = uow
        self._user_repo = user_repo
        self._refresh_repo = refresh_repo
        self._token_issuer = token_issuer

    async def handle(self, cmd: RefreshSessionCommand) -> Result[SessionDTO]:
        if not cmd.refresh_token:
            return Result.failure(
                ApplicationError(
                    code="INVALID_REFRESH_TOKEN",
                    message="Refresh token ausente o inválido.",
                )
            )

        token_hash = self._token_issuer.hash_token(cmd.refresh_token)
        now = datetime.now(UTC)

        async with self._uow:
            rt = await self._refresh_repo.get_by_hash(token_hash)
            if rt is None or rt.expires_at <= now:
                return Result.failure(
                    ApplicationError(
                        code="INVALID_REFRESH_TOKEN",
                        message="Refresh token inválido o expirado.",
                    )
                )

            user = await self._user_repo.get_by_id(rt.user_id)
            if user is None or user.deleted_at is not None:
                return Result.failure(
                    ApplicationError(
                        code="INVALID_REFRESH_TOKEN",
                        message="Refresh token inválido.",
                    )
                )

            if rt.revoked_at is not None:
                elapsed = (now - rt.revoked_at).total_seconds()
                if rt.replaced_by_hash is not None and elapsed <= self.TAB_RACE_WINDOW_SECONDS:
                    raw_refresh, new_hash = self._token_issuer.new_refresh()
                    new_rt = RefreshToken(
                        id=uuid4(),
                        user_id=user.id.value,
                        token_hash=new_hash,
                        expires_at=now + timedelta(days=7),
                        created_at=now,
                    )
                    await self._refresh_repo.add(new_rt)
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

                await self._refresh_repo.revoke_all_for_user(user.id.value, now)
                await self._uow.commit()
                return Result.failure(
                    ApplicationError(
                        code="INVALID_REFRESH_TOKEN",
                        message="Se detectó reutilización de un refresh token revocado.",
                    )
                )

            raw_refresh, new_hash = self._token_issuer.new_refresh()
            rt.rotate(new_hash, now)
            await self._refresh_repo.save(rt)

            new_rt = RefreshToken(
                id=uuid4(),
                user_id=user.id.value,
                token_hash=new_hash,
                expires_at=now + timedelta(days=7),
                created_at=now,
            )
            await self._refresh_repo.add(new_rt)
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
