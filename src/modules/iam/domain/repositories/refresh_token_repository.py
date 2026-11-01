from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.modules.iam.domain.model.entities.refresh_token import RefreshToken


class RefreshTokenRepository(Protocol):
    async def get_by_hash(self, token_hash: str) -> RefreshToken | None: ...

    async def add(self, token: RefreshToken) -> None: ...

    async def save(self, token: RefreshToken) -> None: ...

    async def revoke_all_for_user(self, user_id: UUID, now: datetime) -> None: ...

    async def delete_expired(self, before: datetime) -> int: ...
