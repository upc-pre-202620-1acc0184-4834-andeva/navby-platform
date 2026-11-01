from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Request

from src.shared.application.application_error import ApplicationError
from src.shared.application.current_user import CurrentUser
from src.shared.infrastructure.settings import Settings, get_settings
from src.shared.interfaces.http_errors import ProblemHttpError


async def get_current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise ProblemHttpError(
            error=ApplicationError(
                code="UNAUTHENTICATED",
                message="Falta el token de acceso o es inválido.",
            ),
            instance=request.url.path,
        )
    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise ProblemHttpError(
            error=ApplicationError(
                code="UNAUTHENTICATED",
                message="Falta el token de acceso o es inválido.",
            ),
            instance=request.url.path,
        )
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["sub", "email", "ev", "exp"]},
        )
        user_id = UUID(str(payload["sub"]))
        email = str(payload["email"])
        email_verified = bool(payload["ev"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise ProblemHttpError(
            error=ApplicationError(
                code="UNAUTHENTICATED",
                message="El token de acceso es inválido o expiró.",
            ),
            instance=request.url.path,
        ) from exc

    user = CurrentUser(user_id=user_id, email=email, email_verified=email_verified)
    request.state.current_user = user
    return user


async def get_verified_user(
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    if not user.email_verified:
        raise ProblemHttpError(
            error=ApplicationError(
                code="EMAIL_NOT_VERIFIED",
                message="Debes verificar tu correo electrónico antes de realizar esta operación.",
            ),
            instance=request.url.path,
        )
    return user
