from dataclasses import dataclass

from src.shared.domain.domain_error import DomainError


@dataclass(frozen=True, slots=True)
class PasswordHash:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.startswith("$2"):
            raise DomainError("VALIDATION_ERROR", "Invalid bcrypt password hash.")
