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
