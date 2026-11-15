from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "change-me-local-only-32-bytes-minimum"
REQUIRED_IN_PRODUCTION = (
    "api_public_url",
    "google_client_id",
    "flight_api_key",
    "mercadopago_access_token",
    "mercadopago_webhook_secret",
    "resend_api_key",
)


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

    jwt_secret: str = DEFAULT_JWT_SECRET
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
    resend_from_email: str = "Navby <no-reply@andeva.tech>"

    def production_problems(self) -> list[str]:
        # Solo nombres, nunca valores: el resultado termina en el log de arranque.
        if self.app_env != "production":
            return []
        problems: list[str] = []
        if self.jwt_secret == DEFAULT_JWT_SECRET or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE")
        if not self.webapp_url.startswith("https://"):
            problems.append("WEBAPP_URL")
        problems.extend(name.upper() for name in REQUIRED_IN_PRODUCTION if not getattr(self, name))
        return problems


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
