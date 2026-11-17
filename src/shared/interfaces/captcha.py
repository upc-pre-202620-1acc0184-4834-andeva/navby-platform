import logging
from typing import Annotated

import httpx
from fastapi import Depends, Request

from src.shared.application.application_error import ApplicationError
from src.shared.infrastructure.settings import Settings, get_settings
from src.shared.interfaces.http_errors import ProblemHttpError
from src.shared.interfaces.rate_limit import client_ip_key

logger = logging.getLogger(__name__)

CAPTCHA_HEADER = "X-Captcha-Response"
SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
MAX_TOKEN_LENGTH = 2048  # límite documentado por Cloudflare


def _reject(request: Request, code: str, message: str) -> ProblemHttpError:
    return ProblemHttpError(
        error=ApplicationError(code=code, message=message),
        instance=request.url.path,
    )


async def require_captcha(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Verifica el token de Cloudflare Turnstile de la cabecera X-Captcha-Response."""
    # Sin secreto no se verifica (solo local; en producción la API no arranca sin él).
    if not settings.turnstile_secret_key:
        return

    token = request.headers.get(CAPTCHA_HEADER, "")
    if not token or len(token) > MAX_TOKEN_LENGTH:
        raise _reject(request, "CAPTCHA_INVALID", "Completa la verificación de seguridad.")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                SITEVERIFY_URL,
                data={
                    "secret": settings.turnstile_secret_key,
                    "response": token,
                    "remoteip": client_ip_key(request, settings),
                },
            )
            response.raise_for_status()
            outcome = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Turnstile siteverify failed: %s", type(exc).__name__)
        raise _reject(
            request,
            "PROVIDER_UNAVAILABLE",
            "No se pudo comprobar la verificación de seguridad. Inténtalo de nuevo.",
        ) from exc

    if outcome.get("success") is not True:
        raise _reject(request, "CAPTCHA_INVALID", "La verificación de seguridad no es válida.")
