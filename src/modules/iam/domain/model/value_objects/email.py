import re
from dataclasses import dataclass

from src.shared.domain.domain_error import DomainError

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True, slots=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        object.__setattr__(self, "value", normalized)
        if not normalized or len(normalized) > 254 or not _EMAIL_RE.match(normalized):
            raise DomainError("VALIDATION_ERROR", "El formato del correo electrónico no es válido.")

    @property
    def domain(self) -> str:
        return self.value.split("@", 1)[1]
