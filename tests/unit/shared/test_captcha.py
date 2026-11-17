import httpx
import pytest
import respx
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from src.shared.infrastructure.settings import Settings, get_settings
from src.shared.interfaces.captcha import CAPTCHA_HEADER, SITEVERIFY_URL, require_captcha
from src.shared.interfaces.http_errors import register_exception_handlers

SECRET = "0x-real-secret"


def _client(secret: str) -> AsyncClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/protected", dependencies=[Depends(require_captcha)])
    async def protected() -> dict[str, str]:
        return {"status": "ok"}

    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, turnstile_secret_key=secret
    )
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_without_secret_the_captcha_is_not_checked() -> None:
    async with _client("") as client:
        r = await client.post("/protected")
    assert r.status_code == 200


@pytest.mark.parametrize("headers", [{}, {CAPTCHA_HEADER: ""}, {CAPTCHA_HEADER: "x" * 2049}])
async def test_missing_or_oversized_token_is_rejected_without_calling_cloudflare(
    headers: dict[str, str],
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(SITEVERIFY_URL)
        async with _client(SECRET) as client:
            r = await client.post("/protected", headers=headers)
    assert r.status_code == 400
    assert r.json()["code"] == "CAPTCHA_INVALID"
    assert not route.called


@respx.mock
async def test_valid_token_passes_and_sends_secret_token_and_ip() -> None:
    route = respx.post(SITEVERIFY_URL).mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    async with _client(SECRET) as client:
        r = await client.post("/protected", headers={CAPTCHA_HEADER: "good-token"})
    assert r.status_code == 200
    sent = route.calls.last.request.content.decode()
    assert f"secret={SECRET}" in sent
    assert "response=good-token" in sent
    assert "remoteip=" in sent


@respx.mock
async def test_token_rejected_by_cloudflare_returns_captcha_invalid() -> None:
    respx.post(SITEVERIFY_URL).mock(
        return_value=httpx.Response(
            200, json={"success": False, "error-codes": ["invalid-input-response"]}
        )
    )
    async with _client(SECRET) as client:
        r = await client.post("/protected", headers={CAPTCHA_HEADER: "bad-token"})
    assert r.status_code == 400
    assert r.json()["code"] == "CAPTCHA_INVALID"
    assert SECRET not in r.text


@respx.mock
async def test_cloudflare_down_returns_provider_unavailable() -> None:
    respx.post(SITEVERIFY_URL).mock(side_effect=httpx.ConnectError("down"))
    async with _client(SECRET) as client:
        r = await client.post("/protected", headers={CAPTCHA_HEADER: "any-token"})
    assert r.status_code == 503
    assert r.json()["code"] == "PROVIDER_UNAVAILABLE"
