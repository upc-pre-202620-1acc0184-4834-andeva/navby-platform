from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status

from src.modules.iam.application.acl.ports.disposable_email_policy import (
    DisposableEmailPolicy,
)
from src.modules.iam.application.acl.ports.email_sender import EmailSender
from src.modules.iam.application.acl.ports.google_identity_verifier import (
    GoogleIdentityVerifier,
)
from src.modules.iam.application.acl.ports.one_time_code_store import OneTimeCodeStore
from src.modules.iam.application.acl.ports.password_hasher import PasswordHasher
from src.modules.iam.application.acl.ports.token_issuer import TokenIssuer
from src.modules.iam.application.commands.delete_my_account import (
    DeleteMyAccountCommand,
    DeleteMyAccountHandler,
)
from src.modules.iam.application.commands.login_with_google import (
    LoginWithGoogleCommand,
    LoginWithGoogleHandler,
)
from src.modules.iam.application.commands.login_with_password import (
    LoginWithPasswordCommand,
    LoginWithPasswordHandler,
)
from src.modules.iam.application.commands.logout import LogoutCommand, LogoutHandler
from src.modules.iam.application.commands.refresh_session import (
    RefreshSessionCommand,
    RefreshSessionHandler,
)
from src.modules.iam.application.commands.register_user import (
    RegisterUserCommand,
    RegisterUserHandler,
)
from src.modules.iam.application.commands.request_password_reset import (
    RequestPasswordResetCommand,
    RequestPasswordResetHandler,
)
from src.modules.iam.application.commands.resend_verification import (
    ResendVerificationCommand,
    ResendVerificationHandler,
)
from src.modules.iam.application.commands.reset_password import (
    ResetPasswordCommand,
    ResetPasswordHandler,
)
from src.modules.iam.application.commands.verify_email import (
    VerifyEmailCommand,
    VerifyEmailHandler,
)
from src.modules.iam.application.queries.get_my_profile import (
    GetMyProfileHandler,
    GetMyProfileQuery,
)
from src.modules.iam.infrastructure.adapters.bcrypt_password_hasher import (
    BcryptPasswordHasher,
)
from src.modules.iam.infrastructure.adapters.email_sender_adapters import (
    LogEmailSender,
    ResendEmailSender,
)
from src.modules.iam.infrastructure.adapters.file_disposable_email_policy import (
    FileDisposableEmailPolicy,
)
from src.modules.iam.infrastructure.adapters.google_auth_verifier import (
    GoogleAuthVerifier,
)
from src.modules.iam.infrastructure.adapters.jwt_token_issuer import JwtTokenIssuer
from src.modules.iam.infrastructure.cache.redis_one_time_code_store import (
    RedisOneTimeCodeStore,
)
from src.modules.iam.infrastructure.persistence.sqlalchemy_refresh_token_repository import (
    SqlAlchemyRefreshTokenRepository,
)
from src.modules.iam.infrastructure.persistence.sqlalchemy_user_repository import (
    SqlAlchemyUserRepository,
)
from src.modules.iam.interfaces.rest.assemblers import (
    to_register_response,
    to_session_response,
    to_user_profile_response,
)
from src.modules.iam.interfaces.rest.schemas import (
    DeleteAccountRequest,
    ForgotPasswordRequest,
    GoogleAuthRequest,
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SessionResponse,
    UserProfileResponse,
    VerifyEmailRequest,
)
from src.shared.application.current_user import CurrentUser
from src.shared.infrastructure.database import get_session_factory
from src.shared.infrastructure.redis_client import get_redis_client
from src.shared.infrastructure.settings import Settings, get_settings
from src.shared.infrastructure.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from src.shared.interfaces.auth import get_current_user
from src.shared.interfaces.http_errors import raise_for_error
from src.shared.interfaces.problem_details import ProblemDetails
from src.shared.interfaces.rate_limit import client_ip_key, rate_limit

router = APIRouter(tags=["iam"])

_password_hasher = BcryptPasswordHasher(cost_factor=12)
_disposable_policy = FileDisposableEmailPolicy()


def get_uow() -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(get_session_factory())


def get_password_hasher() -> PasswordHasher:
    return _password_hasher


def get_disposable_policy() -> DisposableEmailPolicy:
    return _disposable_policy


def get_otp_store() -> OneTimeCodeStore:
    return RedisOneTimeCodeStore(get_redis_client())


def get_token_issuer(
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenIssuer:
    return JwtTokenIssuer(secret=settings.jwt_secret, access_ttl_seconds=900)


def get_email_sender(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmailSender:
    if settings.app_env == "local" or not settings.resend_api_key:
        return LogEmailSender()
    return ResendEmailSender(
        api_key=settings.resend_api_key,
        from_email=settings.resend_from_email,
    )


def get_google_verifier(
    settings: Annotated[Settings, Depends(get_settings)],
) -> GoogleIdentityVerifier:
    return GoogleAuthVerifier(client_id=settings.google_client_id)


def _set_refresh_cookie(response: Response, refresh_token: str, settings: Settings) -> None:
    response.set_cookie(
        key="navby_refresh",
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/api/v1/auth",
        max_age=7 * 24 * 3600,
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key="navby_refresh",
        path="/api/v1/auth",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


@router.post(
    "/auth/register",
    summary="Registrar cuenta con correo y contraseña",
    description=(
        "Crea una cuenta nueva en estado `email_verified = false`, valida que el dominio "
        "no sea un correo desechable (`RN-19`), cifra la contraseña con **bcrypt (`cost=12`)** "
        "y envía un código OTP de 6 dígitos por correo (vigencia de 10 minutos en Redis).\n\n"
        "- **Rate limit:** máximo 5 solicitudes por minuto por IP.\n"
        "- **Errores posibles:** `409 EMAIL_ALREADY_REGISTERED`, `422 "
        "DISPOSABLE_EMAIL_NOT_ALLOWED`, "
        "`422 VALIDATION_ERROR` (contraseña < 8 caracteres, sin letras o números, o términos "
        "no aceptados)."
    ),
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("register", client_ip_key, 5))],
    responses={
        409: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
        429: {"model": ProblemDetails},
    },
)
async def register(
    body: RegisterRequest,
    uow: Annotated[SqlAlchemyUnitOfWork, Depends(get_uow)],
    password_hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    disposable_policy: Annotated[DisposableEmailPolicy, Depends(get_disposable_policy)],
    otp_store: Annotated[OneTimeCodeStore, Depends(get_otp_store)],
    email_sender: Annotated[EmailSender, Depends(get_email_sender)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RegisterResponse:
    handler = RegisterUserHandler(
        uow=uow,
        user_repo=SqlAlchemyUserRepository(uow),
        password_hasher=password_hasher,
        disposable_policy=disposable_policy,
        otp_store=otp_store,
        email_sender=email_sender,
    )
    result = await handler.handle(
        RegisterUserCommand(
            email=body.email,
            password=body.password,
            full_name=body.full_name,
            accept_terms=body.accept_terms,
            terms_version=settings.terms_version,
        )
    )
    if result.is_failure:
        raise_for_error(result.error)
    return to_register_response(result.value)


@router.post(
    "/auth/verify-email",
    summary="Verificar correo con código OTP de 6 dígitos",
    description=(
        "Valida el código OTP de 6 dígitos enviado al correo del usuario, marca la cuenta como "
        "`email_verified = true`, publica el evento `iam.user_verified` en el outbox transaccional "
        "(que abre automáticamente su billetera con **10 créditos gratuitos mensuales**, `RN-14`) "
        "y devuelve la sesión activa (`access_token` + cookie `navby_refresh`).\n\n"
        "- **Límite de intentos:** máximo 5 intentos fallidos por código OTP (`OTP_MAX_ATTEMPTS`)."
    ),
    response_model=SessionResponse,
    dependencies=[Depends(rate_limit("otp", client_ip_key, 10))],
    responses={
        400: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
        429: {"model": ProblemDetails},
    },
)
async def verify_email(
    body: VerifyEmailRequest,
    response: Response,
    uow: Annotated[SqlAlchemyUnitOfWork, Depends(get_uow)],
    otp_store: Annotated[OneTimeCodeStore, Depends(get_otp_store)],
    token_issuer: Annotated[TokenIssuer, Depends(get_token_issuer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionResponse:
    handler = VerifyEmailHandler(
        uow=uow,
        user_repo=SqlAlchemyUserRepository(uow),
        refresh_repo=SqlAlchemyRefreshTokenRepository(uow),
        otp_store=otp_store,
        token_issuer=token_issuer,
    )
    result = await handler.handle(VerifyEmailCommand(email=body.email, code=body.code))
    if result.is_failure:
        raise_for_error(result.error)
    _set_refresh_cookie(response, result.value.refresh_token, settings)
    return to_session_response(result.value)


@router.post(
    "/auth/verify-email/resend",
    summary="Reenviar código OTP de verificación",
    description=(
        "Genera y envía un nuevo código OTP de 6 dígitos si la cuenta existe y aún no está "
        "verificada. "
        "Por seguridad responde siempre `202 Accepted` sin revelar si el correo existe y aplica un "
        "enfriamiento (*cooldown*) de 60 segundos en Redis."
    ),
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("otp", client_ip_key, 10))],
    responses={
        422: {"model": ProblemDetails},
        429: {"model": ProblemDetails},
    },
)
async def resend_verification(
    body: ResendVerificationRequest,
    uow: Annotated[SqlAlchemyUnitOfWork, Depends(get_uow)],
    otp_store: Annotated[OneTimeCodeStore, Depends(get_otp_store)],
    email_sender: Annotated[EmailSender, Depends(get_email_sender)],
) -> dict[str, str]:
    handler = ResendVerificationHandler(
        uow=uow,
        user_repo=SqlAlchemyUserRepository(uow),
        otp_store=otp_store,
        email_sender=email_sender,
    )
    await handler.handle(ResendVerificationCommand(email=body.email))
    return {"status": "accepted"}


@router.post(
    "/auth/login",
    summary="Iniciar sesión con correo y contraseña",
    description=(
        "Autentica al usuario verificando su hash bcrypt y emite un **`access_token` JWT "
        "(HS256, 15 min)** "
        "junto con la cookie `HttpOnly` `navby_refresh` (7 días, `SameSite=Strict`).\n\n"
        "- 💡 **Para probar en `/docs`:** haz clic en **Try it out** → **Execute** con las "
        "credenciales "
        "precargadas (`demo.azure@mail.com` / `Viajar2026`), copia el `access_token` y "
        "pégalo en el botón **`Authorize 🔒`**.\n"
        "- **Errores posibles:** `401 INVALID_CREDENTIALS`, `403 EMAIL_NOT_VERIFIED`, `429 "
        "RATE_LIMITED`."
    ),
    response_model=SessionResponse,
    dependencies=[Depends(rate_limit("login", client_ip_key, 10))],
    responses={
        401: {"model": ProblemDetails},
        403: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
        429: {"model": ProblemDetails},
    },
)
async def login(
    body: LoginRequest,
    response: Response,
    uow: Annotated[SqlAlchemyUnitOfWork, Depends(get_uow)],
    password_hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    token_issuer: Annotated[TokenIssuer, Depends(get_token_issuer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionResponse:
    handler = LoginWithPasswordHandler(
        uow=uow,
        user_repo=SqlAlchemyUserRepository(uow),
        refresh_repo=SqlAlchemyRefreshTokenRepository(uow),
        password_hasher=password_hasher,
        token_issuer=token_issuer,
    )
    result = await handler.handle(
        LoginWithPasswordCommand(email=body.email, password=body.password)
    )
    if result.is_failure:
        raise_for_error(result.error)
    _set_refresh_cookie(response, result.value.refresh_token, settings)
    return to_session_response(result.value)


@router.post(
    "/auth/google",
    summary="Iniciar sesión o registrarse con Google OAuth 2.0",
    description=(
        "Verifica la firma criptográfica RS256 del `id_token` emitido por Google Identity "
        "Services.\n\n"
        "- Si el correo ya existe en Navby, vincula el `google_sub` (si aún no lo tenía) e "
        "inicia sesión.\n"
        "- Si el usuario es nuevo, exige `accept_terms = true`, crea la cuenta verificada y "
        "abre su billetera inicial."
    ),
    response_model=SessionResponse,
    dependencies=[Depends(rate_limit("login", client_ip_key, 10))],
    responses={
        401: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
        429: {"model": ProblemDetails},
    },
)
async def login_google(
    body: GoogleAuthRequest,
    response: Response,
    uow: Annotated[SqlAlchemyUnitOfWork, Depends(get_uow)],
    google_verifier: Annotated[GoogleIdentityVerifier, Depends(get_google_verifier)],
    disposable_policy: Annotated[DisposableEmailPolicy, Depends(get_disposable_policy)],
    token_issuer: Annotated[TokenIssuer, Depends(get_token_issuer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionResponse:
    handler = LoginWithGoogleHandler(
        uow=uow,
        user_repo=SqlAlchemyUserRepository(uow),
        refresh_repo=SqlAlchemyRefreshTokenRepository(uow),
        google_verifier=google_verifier,
        disposable_policy=disposable_policy,
        token_issuer=token_issuer,
    )
    result = await handler.handle(
        LoginWithGoogleCommand(
            id_token=body.id_token,
            accept_terms=body.accept_terms,
            terms_version=settings.terms_version,
        )
    )
    if result.is_failure:
        raise_for_error(result.error)
    _set_refresh_cookie(response, result.value.refresh_token, settings)
    return to_session_response(result.value)


@router.post(
    "/auth/refresh",
    summary="Renovar access_token rotando la cookie navby_refresh",
    description=(
        "Lee el refresh token desde la cookie `HttpOnly` `navby_refresh`, rota el token "
        "dentro de la misma "
        "familia (`family_id`) y emite un nuevo `access_token` de 15 minutos.\n\n"
        "- **Detección de robo de sesión:** si se presenta un refresh token ya "
        "rotado/revocado, se revoca "
        "toda la familia de tokens del dispositivo y se limpia la cookie (`401 UNAUTHENTICATED`)."
    ),
    response_model=SessionResponse,
    responses={
        401: {"model": ProblemDetails},
    },
)
async def refresh_session(
    response: Response,
    uow: Annotated[SqlAlchemyUnitOfWork, Depends(get_uow)],
    token_issuer: Annotated[TokenIssuer, Depends(get_token_issuer)],
    settings: Annotated[Settings, Depends(get_settings)],
    navby_refresh: Annotated[str | None, Cookie()] = None,
) -> SessionResponse:
    handler = RefreshSessionHandler(
        uow=uow,
        user_repo=SqlAlchemyUserRepository(uow),
        refresh_repo=SqlAlchemyRefreshTokenRepository(uow),
        token_issuer=token_issuer,
    )
    result = await handler.handle(RefreshSessionCommand(refresh_token=navby_refresh))
    if result.is_failure:
        _clear_refresh_cookie(response, settings)
        raise_for_error(result.error)
    _set_refresh_cookie(response, result.value.refresh_token, settings)
    return to_session_response(result.value)


@router.post(
    "/auth/logout",
    summary="Cerrar sesión y revocar familia de refresh tokens",
    description=(
        "Revoca la familia de refresh tokens asociada a la cookie `navby_refresh` y elimina "
        "la cookie del navegador. "
        "Es idempotente y siempre devuelve `204 No Content`."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        500: {"model": ProblemDetails},
    },
)
async def logout(
    response: Response,
    uow: Annotated[SqlAlchemyUnitOfWork, Depends(get_uow)],
    token_issuer: Annotated[TokenIssuer, Depends(get_token_issuer)],
    settings: Annotated[Settings, Depends(get_settings)],
    navby_refresh: Annotated[str | None, Cookie()] = None,
) -> None:
    handler = LogoutHandler(
        uow=uow,
        refresh_repo=SqlAlchemyRefreshTokenRepository(uow),
        token_issuer=token_issuer,
    )
    await handler.handle(LogoutCommand(refresh_token=navby_refresh))
    _clear_refresh_cookie(response, settings)


@router.post(
    "/auth/forgot-password",
    summary="Solicitar enlace de restablecimiento de contraseña",
    description=(
        "Genera un token criptográfico de 64 caracteres hexadecimales con vigencia de 15 "
        "minutos en Redis "
        "y envía el enlace de recuperación al correo del usuario. Siempre responde `202 "
        "Accepted` para "
        "evitar enumeración de cuentas.\n\n"
        "- **Rate limit:** máximo 3 solicitudes por minuto por IP."
    ),
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("forgot_password", client_ip_key, 3))],
    responses={
        422: {"model": ProblemDetails},
        429: {"model": ProblemDetails},
    },
)
async def forgot_password(
    body: ForgotPasswordRequest,
    uow: Annotated[SqlAlchemyUnitOfWork, Depends(get_uow)],
    otp_store: Annotated[OneTimeCodeStore, Depends(get_otp_store)],
    email_sender: Annotated[EmailSender, Depends(get_email_sender)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    handler = RequestPasswordResetHandler(
        uow=uow,
        user_repo=SqlAlchemyUserRepository(uow),
        otp_store=otp_store,
        email_sender=email_sender,
    )
    await handler.handle(
        RequestPasswordResetCommand(email=body.email, webapp_url=settings.webapp_url)
    )
    return {"status": "accepted"}


@router.post(
    "/auth/reset-password",
    summary="Restablecer contraseña usando token de recuperación",
    description=(
        "Consume el token de recuperación de un solo uso, actualiza la contraseña cifrada "
        "con bcrypt "
        "y revoca todas las sesiones activas (`refresh_tokens`) del usuario."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("otp", client_ip_key, 10))],
    responses={
        400: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
        429: {"model": ProblemDetails},
    },
)
async def reset_password(
    body: ResetPasswordRequest,
    uow: Annotated[SqlAlchemyUnitOfWork, Depends(get_uow)],
    otp_store: Annotated[OneTimeCodeStore, Depends(get_otp_store)],
    password_hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
) -> None:
    handler = ResetPasswordHandler(
        uow=uow,
        user_repo=SqlAlchemyUserRepository(uow),
        refresh_repo=SqlAlchemyRefreshTokenRepository(uow),
        otp_store=otp_store,
        password_hasher=password_hasher,
    )
    result = await handler.handle(
        ResetPasswordCommand(token=body.token, new_password=body.new_password)
    )
    if result.is_failure:
        raise_for_error(result.error)


@router.get(
    "/users/me",
    summary="Obtener perfil del usuario autenticado",
    description=(
        "Devuelve los datos de perfil de la cuenta autenticada (`user_id`, `email`, `full_name`, "
        "`email_verified`, métodos de acceso configurados `has_password` / `has_google` y "
        "`created_at`).\n\n"
        "- 🔒 **Requiere autenticación:** `Authorization: Bearer <access_token>`."
    ),
    response_model=UserProfileResponse,
    responses={
        401: {"model": ProblemDetails},
    },
)
async def get_my_profile(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    uow: Annotated[SqlAlchemyUnitOfWork, Depends(get_uow)],
) -> UserProfileResponse:
    handler = GetMyProfileHandler(
        uow=uow,
        user_repo=SqlAlchemyUserRepository(uow),
    )
    result = await handler.handle(GetMyProfileQuery(user_id=current_user.user_id))
    if result.is_failure:
        raise_for_error(result.error)
    return to_user_profile_response(result.value)


@router.delete(
    "/users/me",
    summary="Eliminar cuenta propia de forma permanente",
    description=(
        'Elimina el registro del usuario tras validar la palabra exacta `"ELIMINAR"`, revoca sus '
        "refresh tokens y publica el evento `iam.user_deleted` en el outbox para anular su "
        "billetera "
        "(`RN-22`) y borrar todos sus itinerarios guardados.\n\n"
        "- 🔒 **Requiere autenticación:** `Authorization: Bearer <access_token>`."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
    },
)
async def delete_my_account(
    body: DeleteAccountRequest,
    response: Response,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    uow: Annotated[SqlAlchemyUnitOfWork, Depends(get_uow)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    handler = DeleteMyAccountHandler(
        uow=uow,
        user_repo=SqlAlchemyUserRepository(uow),
        refresh_repo=SqlAlchemyRefreshTokenRepository(uow),
    )
    result = await handler.handle(
        DeleteMyAccountCommand(
            user_id=current_user.user_id,
            confirmation=body.confirmation,
        )
    )
    if result.is_failure:
        raise_for_error(result.error)
    _clear_refresh_cookie(response, settings)
