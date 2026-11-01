from dataclasses import dataclass

from src.shared.domain.domain_error import DomainError


@dataclass(frozen=True, slots=True)
class Coordinates:
    lat: float
    lon: float

    def __post_init__(self) -> None:
        if not (-90.0 <= self.lat <= 90.0):
            raise DomainError("VALIDATION_ERROR", f"Invalid latitude: {self.lat}")
        if not (-180.0 <= self.lon <= 180.0):
            raise DomainError("VALIDATION_ERROR", f"Invalid longitude: {self.lon}")
