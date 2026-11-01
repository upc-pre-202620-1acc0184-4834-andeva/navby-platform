from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError

from src.main import create_app
from src.shared.infrastructure.redis_client import get_shared_redis


class BrokenRedis:
    async def ping(self) -> bool:
        raise RedisConnectionError("Redis is down")


async def test_ts23_health_all_operational() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {
            "status": "UP",
            "postgres": "UP",
            "redis": "UP",
            "graph": {
                "status": "UP",
                "nodes": 3354,
                "edges": 37326,
            },
        }


async def test_ts23_health_redis_down_returns_503() -> None:
    app = create_app()
    app.dependency_overrides[get_shared_redis] = lambda: BrokenRedis()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "DOWN"
        assert body["redis"] == "DOWN"
        assert body["postgres"] == "UP"
        assert body["graph"] == {
            "status": "UP",
            "nodes": 3354,
            "edges": 37326,
        }
