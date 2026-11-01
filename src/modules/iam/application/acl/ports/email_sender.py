from typing import Protocol


class EmailSender(Protocol):
    async def send_verification_code(self, email: str, code: str) -> None: ...

    async def send_password_reset(self, email: str, link: str) -> None: ...
