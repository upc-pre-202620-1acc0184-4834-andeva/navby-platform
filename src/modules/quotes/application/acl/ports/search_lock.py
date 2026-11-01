from typing import Protocol
from uuid import UUID


class SearchLock(Protocol):
    async def acquire(self, user_id: UUID) -> bool: ...

    async def release(self, user_id: UUID) -> None: ...
