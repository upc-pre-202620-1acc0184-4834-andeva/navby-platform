from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "local"
    database_url: str = "postgresql+asyncpg://navby:navby@localhost:5432/navby"
    redis_url: str = "redis://localhost:6379/0"
    postgres_port: int = 5432

    jwt_secret: str = "change-me-local-only-32-bytes-minimum"
    cookie_secure: bool = False
    trust_proxy_headers: bool = False
    terms_version: str = "2026-10"

    webapp_url: str = "http://localhost:5173/app"
    api_public_url: str = ""

    google_client_id: str = ""
    flight_api_key: str = ""
    flight_api_max_concurrency: int = 5

    mercadopago_access_token: str = ""
    mercadopago_webhook_secret: str = ""

    resend_api_key: str = ""
    resend_from_email: str = "Navby <no-reply@navby.andeva.tech>"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
