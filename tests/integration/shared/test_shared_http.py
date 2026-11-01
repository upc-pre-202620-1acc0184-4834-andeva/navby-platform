from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

import jwt
import pytest
from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, ConfigDict

from src.shared.application.application_error import ApplicationError
from src.shared.application.current_user import CurrentUser
from src.shared.application.result import Result
from src.shared.infrastructure.redis_client import get_redis_client
from src.shared.infrastructure.settings import Settings, get_settings
from src.shared.interfaces.auth import get_current_user, get_verified_user
from src.shared.interfaces.http_errors import register_exception_handlers, to_http
from src.shared.interfaces.rate_limit import client_ip_key, rate_limit


class DummyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: int


def build_test_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: settings
    register_exception_handlers(app)

    @app.get("/api/v1/quotes/search")
    async def fail_credits(request: Request) -> dict[str, str]:
        res: Result[dict[str, str]] = Result.failure(
            ApplicationError(
                code="INSUFFICIENT_CREDITS",
                message="Se requieren 5 créditos y la billetera tiene 3.",
            )
        )
        if not res.is_success:
            raise to_http(res, request)
        return res.value

    @app.get("/api/v1/boom")
    async def boom() -> dict[str, str]:
        raise RuntimeError("secret database stacktrace details")

    @app.post("/api/v1/validate")
    async def validate_body(body: DummyPayload) -> dict[str, int]:
        return {"amount": body.amount}

    @app.get("/api/v1/me")
    async def me(
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> dict[str, str]:
        return {"user_id": str(user.user_id), "email": user.email}

    @app.get("/api/v1/verified-only")
    async def verified_only(
        user: Annotated[CurrentUser, Depends(get_verified_user)],
    ) -> dict[str, str]:
        return {"user_id": str(user.user_id)}

    @app.post(
        "/api/v1/auth/login",
        dependencies=[Depends(rate_limit("login", client_ip_key, 10))],
    )
    async def login_endpoint() -> dict[str, bool]:
        return {"ok": True}

    return app


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        app_env="local",
        jwt_secret="test-secret-with-at-least-32-bytes-long!!",
    )


async def test_ts33_error_mapping_and_unhandled_exception(test_settings: Settings) -> None:
    app = build_test_app(test_settings)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.get("/api/v1/quotes/search")
        assert r1.status_code == 402
        assert r1.headers["content-type"].startswith("application/problem+json")
        body1 = r1.json()
        assert body1["code"] == "INSUFFICIENT_CREDITS"
        assert body1["status"] == 402
        assert body1["type"] == "https://navby.andeva.tech/errors/INSUFFICIENT_CREDITS"
        assert body1["instance"] == "/api/v1/quotes/search"

        r2 = await client.get("/api/v1/boom")
        assert r2.status_code == 500
        assert r2.headers["content-type"].startswith("application/problem+json")
        body2 = r2.json()
        assert body2["code"] == "INTERNAL_ERROR"
        assert "stacktrace" not in r2.text

        r3 = await client.post("/api/v1/validate", json={"amount": "not-an-int", "extra": 1})
        assert r3.status_code == 422
        body3 = r3.json()
        assert body3["code"] == "VALIDATION_ERROR"
        assert isinstance(body3["invalid_params"], list)
        assert len(body3["invalid_params"]) >= 1


async def test_ts33_authentication_dependencies(test_settings: Settings) -> None:
    app = build_test_app(test_settings)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    user_id = str(uuid4())
    now = datetime.now(UTC)

    valid_verified_token = jwt.encode(
        {
            "sub": user_id,
            "email": "ana@mail.com",
            "ev": True,
            "exp": now + timedelta(minutes=15),
        },
        test_settings.jwt_secret,
        algorithm="HS256",
    )
    unverified_token = jwt.encode(
        {
            "sub": user_id,
            "email": "ana@mail.com",
            "ev": False,
            "exp": now + timedelta(minutes=15),
        },
        test_settings.jwt_secret,
        algorithm="HS256",
    )
    expired_token = jwt.encode(
        {
            "sub": user_id,
            "email": "ana@mail.com",
            "ev": True,
            "exp": now - timedelta(minutes=1),
        },
        test_settings.jwt_secret,
        algorithm="HS256",
    )
    wrong_sig_token = jwt.encode(
        {
            "sub": user_id,
            "email": "ana@mail.com",
            "ev": True,
            "exp": now + timedelta(minutes=15),
        },
        "another-secret-with-at-least-32-bytes-long!!",
        algorithm="HS256",
    )

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_no_jwt = await client.get("/api/v1/me")
        assert r_no_jwt.status_code == 401
        assert r_no_jwt.json()["code"] == "UNAUTHENTICATED"

        r_expired = await client.get(
            "/api/v1/me", headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert r_expired.status_code == 401
        assert r_expired.json()["code"] == "UNAUTHENTICATED"

        r_wrong_sig = await client.get(
            "/api/v1/me", headers={"Authorization": f"Bearer {wrong_sig_token}"}
        )
        assert r_wrong_sig.status_code == 401
        assert r_wrong_sig.json()["code"] == "UNAUTHENTICATED"

        r_unverified = await client.get(
            "/api/v1/verified-only", headers={"Authorization": f"Bearer {unverified_token}"}
        )
        assert r_unverified.status_code == 403
        assert r_unverified.json()["code"] == "EMAIL_NOT_VERIFIED"

        r_ok = await client.get(
            "/api/v1/verified-only",
            headers={"Authorization": f"Bearer {valid_verified_token}"},
        )
        assert r_ok.status_code == 200
        assert r_ok.json()["user_id"] == user_id


async def test_ts33_rate_limiting_11th_login_returns_429(test_settings: Settings) -> None:
    redis = get_redis_client(test_settings)
    keys = await redis.keys("navby:ratelimit:login:*")
    if keys:
        await redis.delete(*keys)

    app = build_test_app(test_settings)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(10):
            resp = await client.post("/api/v1/auth/login")
            assert resp.status_code == 200

        r11 = await client.post("/api/v1/auth/login")
        assert r11.status_code == 429
        assert "Retry-After" in r11.headers
        assert r11.json()["code"] == "RATE_LIMITED"
    await redis.aclose()
