from typing import Any

from src.shared.infrastructure.settings import Settings

VALID_PRODUCTION: dict[str, Any] = {
    "app_env": "production",
    "jwt_secret": "k" * 40,
    "cookie_secure": True,
    "webapp_url": "https://navby.andeva.tech/app",
    "api_public_url": "https://navby-api.example.cloudapp.azure.com",
    "google_client_id": "client-id",
    "flight_api_key": "flight-key",
    "mercadopago_access_token": "TEST-token",
    "mercadopago_webhook_secret": "webhook-secret",
    "resend_api_key": "re_key",
    "turnstile_secret_key": "0x-turnstile-secret",
}

UNSAFE_VALUES: dict[str, Any] = {
    "jwt_secret": "change-me-local-only-32-bytes-minimum",
    "cookie_secure": False,
    "webapp_url": "http://localhost:5173/app",
    "api_public_url": "",
    "google_client_id": "",
    "flight_api_key": "",
    "mercadopago_access_token": "",
    "mercadopago_webhook_secret": "",
    "resend_api_key": "",
    "turnstile_secret_key": "",
}


def _settings(**values: Any) -> Settings:
    return Settings(_env_file=None, **values)


def test_production_with_every_setting_is_safe() -> None:
    assert _settings(**VALID_PRODUCTION).production_problems() == []


def test_production_names_every_unsafe_setting() -> None:
    problems = _settings(**{**VALID_PRODUCTION, **UNSAFE_VALUES}).production_problems()

    assert sorted(problems) == sorted(name.upper() for name in UNSAFE_VALUES)


def test_production_rejects_short_jwt_secret() -> None:
    problems = _settings(**{**VALID_PRODUCTION, "jwt_secret": "short"}).production_problems()

    assert problems == ["JWT_SECRET"]


def test_local_never_reports_problems() -> None:
    assert _settings(**{**UNSAFE_VALUES, "app_env": "local"}).production_problems() == []


def test_production_rejects_turnstile_test_secret() -> None:
    test_secret = "1x0000000000000000000000000000000AA"
    problems = _settings(
        **{**VALID_PRODUCTION, "turnstile_secret_key": test_secret}
    ).production_problems()

    assert problems == ["TURNSTILE_SECRET_KEY"]
