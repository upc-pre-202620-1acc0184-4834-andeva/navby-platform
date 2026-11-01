from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CurrentUser:
    user_id: UUID
    email: str
    email_verified: bool
