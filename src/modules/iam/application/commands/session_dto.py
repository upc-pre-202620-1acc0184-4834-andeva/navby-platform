from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UserSummaryDTO:
    user_id: UUID
    email: str
    full_name: str
    email_verified: bool


@dataclass(frozen=True, slots=True)
class SessionDTO:
    access_token: str
    refresh_token: str
    expires_in: int
    user: UserSummaryDTO
