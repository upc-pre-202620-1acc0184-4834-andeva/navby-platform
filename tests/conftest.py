from collections.abc import AsyncIterator

import pytest

from src.shared.infrastructure.database import close_database
from src.shared.infrastructure.redis_client import RedisClient


@pytest.fixture(autouse=True)
async def _cleanup_async_resources() -> AsyncIterator[None]:
    yield
    await RedisClient.close()
    await close_database()
