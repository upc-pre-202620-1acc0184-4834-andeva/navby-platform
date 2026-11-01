from dataclasses import dataclass

from src.modules.routing.domain.model.value_objects.iata_code import IataCode
from src.shared.domain.domain_error import DomainError


@dataclass(frozen=True, slots=True)
class Edge:
    to: IataCode
    distance_km: float
    minutes: float

    def __post_init__(self) -> None:
        if self.distance_km < 0 or self.minutes <= 0:
            raise DomainError("VALIDATION_ERROR", "Edge distance and minutes must be positive.")

    @staticmethod
    def from_distance(to: IataCode, distance_km: float) -> "Edge":
        minutes = (distance_km / 800.0) * 60.0 + 30.0
        return Edge(to=to, distance_km=distance_km, minutes=minutes)
