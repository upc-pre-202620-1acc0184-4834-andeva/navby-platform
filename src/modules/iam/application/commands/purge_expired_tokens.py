from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from src.modules.iam.domain.repositories.refresh_token_repository import (
    RefreshTokenRepository,
)
from src.shared.application.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class PurgeExpiredTokensCommand:
    now: datetime | None = None


class PurgeExpiredTokensHandler:
    RETENTION_DAYS = 30

    def __init__(
        self,
        uow: UnitOfWork,
        refresh_repo: RefreshTokenRepository,
    ) -> None:
        self._uow = uow
        self._refresh_repo = refresh_repo

    async def handle(self, cmd: PurgeExpiredTokensCommand | None = None) -> int:
        now = cmd.now if cmd and cmd.now else datetime.now(UTC)
        cutoff = now - timedelta(days=self.RETENTION_DAYS)
        async with self._uow:
            deleted = await self._refresh_repo.delete_expired(cutoff)
            await self._uow.commit()
        return deleted
