from dataclasses import dataclass
from datetime import UTC, datetime

from src.modules.iam.application.acl.ports.token_issuer import TokenIssuer
from src.modules.iam.domain.repositories.refresh_token_repository import (
    RefreshTokenRepository,
)
from src.shared.application.result import Result
from src.shared.application.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class LogoutCommand:
    refresh_token: str | None


class LogoutHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        refresh_repo: RefreshTokenRepository,
        token_issuer: TokenIssuer,
    ) -> None:
        self._uow = uow
        self._refresh_repo = refresh_repo
        self._token_issuer = token_issuer

    async def handle(self, cmd: LogoutCommand) -> Result[None]:
        if not cmd.refresh_token:
            return Result.success(None)

        token_hash = self._token_issuer.hash_token(cmd.refresh_token)
        now = datetime.now(UTC)
        async with self._uow:
            rt = await self._refresh_repo.get_by_hash(token_hash)
            if rt is not None and rt.revoked_at is None:
                rt.revoke(now)
                await self._refresh_repo.save(rt)
                await self._uow.commit()

        return Result.success(None)
