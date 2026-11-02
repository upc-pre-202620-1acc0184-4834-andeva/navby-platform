from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RegisterRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "email": "viajero.nuevo@mail.com",
                "password": "Viajar2026",
                "full_name": "Carlos Mendoza",
                "accept_terms": True,
            }
        },
    )

    email: str
    password: str
    full_name: str
    accept_terms: bool


class RegisterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    email: str
    email_verified: bool


class VerifyEmailRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "email": "viajero.nuevo@mail.com",
                "code": "123456",
            }
        },
    )

    email: str
    code: str


class ResendVerificationRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"example": {"email": "viajero.nuevo@mail.com"}},
    )

    email: str


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "email": "demo.azure@mail.com",
                "password": "Viajar2026",
            }
        },
    )

    email: str
    password: str


class GoogleAuthRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "id_token": "eyJhbGciOiJSUzI1NiIsImtpZCI6Ij...",
                "accept_terms": True,
            }
        },
    )

    id_token: str
    accept_terms: bool | None = None


class UserSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    email: str
    full_name: str
    email_verified: bool


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserSummaryResponse


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"example": {"email": "demo.azure@mail.com"}},
    )

    email: str


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "token": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                "new_password": "NuevaPassword2026",
            }
        },
    )

    token: str
    new_password: str


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    email: str
    full_name: str
    email_verified: bool
    has_password: bool
    has_google: bool
    created_at: datetime


class DeleteAccountRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"example": {"confirmation": "ELIMINAR"}},
    )

    confirmation: str
