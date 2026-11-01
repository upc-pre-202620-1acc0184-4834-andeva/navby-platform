from typing import Protocol

from src.modules.iam.domain.model.aggregates.user import User


class TokenIssuer(Protocol):
    def issue_access(self, user: User) -> str: ...

    def new_refresh(self) -> tuple[str, str]: ...

    def hash_token(self, raw_token: str) -> str: ...
