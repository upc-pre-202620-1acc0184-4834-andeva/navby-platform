from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    sub: str
    email: str
    email_verified: bool
    name: str


class GoogleIdentityVerifier(Protocol):
    async def verify(self, id_token: str) -> GoogleIdentity | None: ...
