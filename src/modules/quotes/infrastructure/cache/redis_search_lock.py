from uuid import UUID

from redis.asyncio import Redis

from src.modules.quotes.application.acl.ports.search_lock import SearchLock


class RedisSearchLock(SearchLock):
    TTL_SECONDS = 60

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def acquire(self, user_id: UUID) -> bool:
        key = f"navby:quotes:lock:{user_id}"
        res = await self._redis.set(key, "1", nx=True, ex=self.TTL_SECONDS)
        return res is True

    async def release(self, user_id: UUID) -> None:
        key = f"navby:quotes:lock:{user_id}"
        await self._redis.delete(key)
