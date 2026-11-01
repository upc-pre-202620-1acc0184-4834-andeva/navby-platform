from src.modules.iam.application.commands.register_user import RegisterUserDTO
from src.modules.iam.application.commands.session_dto import SessionDTO
from src.modules.iam.application.queries.get_my_profile import UserProfileDTO
from src.modules.iam.interfaces.rest.schemas import (
    RegisterResponse,
    SessionResponse,
    UserProfileResponse,
    UserSummaryResponse,
)


def to_register_response(dto: RegisterUserDTO) -> RegisterResponse:
    return RegisterResponse(
        user_id=dto.user_id,
        email=dto.email,
        email_verified=dto.email_verified,
    )


def to_session_response(dto: SessionDTO) -> SessionResponse:
    return SessionResponse(
        access_token=dto.access_token,
        token_type="Bearer",
        expires_in=dto.expires_in,
        user=UserSummaryResponse(
            user_id=dto.user.user_id,
            email=dto.user.email,
            full_name=dto.user.full_name,
            email_verified=dto.user.email_verified,
        ),
    )


def to_user_profile_response(dto: UserProfileDTO) -> UserProfileResponse:
    return UserProfileResponse(
        user_id=dto.user_id,
        email=dto.email,
        full_name=dto.full_name,
        email_verified=dto.email_verified,
        has_password=dto.has_password,
        has_google=dto.has_google,
        created_at=dto.created_at,
    )
