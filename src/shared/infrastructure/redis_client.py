import asyncio

from redis.asyncio import Redis

from src.shared.infrastructure.settings import Settings, get_settings


class RedisClient:
    _instance: Redis | None = None
    _bound_loop: asyncio.AbstractEventLoop | None = None

    @classmethod
    def get(cls, settings: Settings | None = None) -> Redis:
        try:
            loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if cls._instance is None or (loop is not None and loop is not cls._bound_loop):
            cfg = settings or get_settings()
            cls._instance = Redis.from_url(cfg.redis_url, decode_responses=True)
            cls._bound_loop = loop
        return cls._instance

    @classmethod
    async def close(cls) -> None:
        if cls._instance is not None:
            await cls._instance.aclose()
            cls._instance = None
            cls._bound_loop = None


def get_redis_client(settings: Settings | None = None) -> Redis:
    cfg = settings or get_settings()
    return Redis.from_url(cfg.redis_url, decode_responses=True)


def get_shared_redis() -> Redis:
    return RedisClient.get()
