import bcrypt

from src.modules.iam.application.acl.ports.password_hasher import PasswordHasher
from src.modules.iam.domain.model.value_objects.password_hash import PasswordHash
from src.modules.iam.domain.model.value_objects.plain_password import PlainPassword

_DUMMY_HASH = bcrypt.hashpw(b"navby-dummy-password-2026", bcrypt.gensalt(rounds=12))


class BcryptPasswordHasher(PasswordHasher):
    def __init__(self, cost_factor: int = 12) -> None:
        self._cost_factor = cost_factor

    def hash(self, plain: PlainPassword) -> PasswordHash:
        salt = bcrypt.gensalt(rounds=self._cost_factor)
        hashed = bcrypt.hashpw(plain.value.encode("utf-8"), salt).decode("utf-8")
        return PasswordHash(hashed)

    def verify(self, plain: str, password_hash: PasswordHash) -> bool:
        try:
            return bcrypt.checkpw(
                plain.encode("utf-8"),
                password_hash.value.encode("utf-8"),
            )
        except ValueError:
            return False

    def dummy_verify(self, plain: str) -> None:
        bcrypt.checkpw(plain.encode("utf-8"), _DUMMY_HASH)
