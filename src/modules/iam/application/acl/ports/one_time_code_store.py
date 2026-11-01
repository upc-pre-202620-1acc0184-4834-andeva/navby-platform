from enum import StrEnum
from typing import Protocol
from uuid import UUID


class OtpCheck(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"
    EXHAUSTED = "EXHAUSTED"


class OneTimeCodeStore(Protocol):
    async def save_otp(self, user_id: UUID, code_hash: str) -> None: ...

    async def check_otp(self, user_id: UUID, code: str) -> OtpCheck: ...

    async def can_resend_otp(self, email_hash: str) -> bool: ...

    async def mark_resend_otp(self, email_hash: str) -> None: ...

    async def save_reset(self, token_hash: str, user_id: UUID) -> None: ...

    async def peek_reset(self, token_hash: str) -> UUID | None: ...

    async def consume_reset(self, token_hash: str) -> UUID | None: ...
