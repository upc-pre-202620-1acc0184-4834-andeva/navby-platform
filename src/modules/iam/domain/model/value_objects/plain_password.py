from dataclasses import dataclass

from src.shared.domain.domain_error import DomainError


@dataclass(frozen=True, slots=True)
class PlainPassword:
    value: str

    def __post_init__(self) -> None:
        if not (8 <= len(self.value) <= 72):
            raise DomainError(
                "VALIDATION_ERROR",
                "La contraseña debe tener entre 8 y 72 caracteres.",
            )
        has_letter = any(ch.isalpha() for ch in self.value)
        has_digit = any(ch.isdigit() for ch in self.value)
        if not (has_letter and has_digit):
            raise DomainError(
                "VALIDATION_ERROR",
                "La contraseña debe incluir al menos una letra y un dígito.",
            )

    def __repr__(self) -> str:
        return "PlainPassword('***')"
