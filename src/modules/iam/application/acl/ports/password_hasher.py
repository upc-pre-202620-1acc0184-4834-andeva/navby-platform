from typing import Protocol

from src.modules.iam.domain.model.value_objects.password_hash import PasswordHash
from src.modules.iam.domain.model.value_objects.plain_password import PlainPassword


class PasswordHasher(Protocol):
    def hash(self, plain: PlainPassword) -> PasswordHash: ...

    def verify(self, plain: str, password_hash: PasswordHash) -> bool: ...

    def dummy_verify(self, plain: str) -> None: ...
