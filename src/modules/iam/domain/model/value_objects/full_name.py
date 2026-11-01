from dataclasses import dataclass

from src.shared.domain.domain_error import DomainError


@dataclass(frozen=True, slots=True)
class FullName:
    value: str

    def __post_init__(self) -> None:
        cleaned = self.value.strip()
        object.__setattr__(self, "value", cleaned)
        if not (1 <= len(cleaned) <= 100):
            raise DomainError(
                "VALIDATION_ERROR",
                "El nombre completo debe tener entre 1 y 100 caracteres.",
            )
