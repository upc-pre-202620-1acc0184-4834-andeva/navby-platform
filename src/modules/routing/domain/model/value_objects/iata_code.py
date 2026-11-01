import re
from dataclasses import dataclass

from src.shared.domain.domain_error import DomainError

_IATA_RE = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True, slots=True, order=True)
class IataCode:
    value: str

    def __post_init__(self) -> None:
        if not _IATA_RE.match(self.value):
            raise DomainError("VALIDATION_ERROR", f"Invalid IATA code: {self.value}")

    def __str__(self) -> str:
        return self.value
