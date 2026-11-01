from dataclasses import dataclass

from src.shared.domain.domain_error import DomainError


@dataclass(frozen=True, slots=True)
class ItineraryName:
    value: str

    def __post_init__(self) -> None:
        cleaned = self.value.strip()
        if not (1 <= len(cleaned) <= 80):
            raise DomainError(
                "VALIDATION_ERROR",
                "El nombre del itinerario debe tener entre 1 y 80 caracteres.",
            )
        object.__setattr__(self, "value", cleaned)
