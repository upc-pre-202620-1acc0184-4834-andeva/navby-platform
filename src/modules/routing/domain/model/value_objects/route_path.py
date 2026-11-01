from dataclasses import dataclass

from src.modules.routing.domain.model.value_objects.iata_code import IataCode
from src.shared.domain.domain_error import DomainError


@dataclass(frozen=True, slots=True)
class RoutePath:
    airports: tuple[IataCode, ...]
    t_min_minutes: int
    nodes_expanded: int

    def __post_init__(self) -> None:
        if not (2 <= len(self.airports) <= 4):
            raise DomainError("VALIDATION_ERROR", "RoutePath must have 2 to 4 airports.")
        if len(set(self.airports)) != len(self.airports):
            raise DomainError("VALIDATION_ERROR", "RoutePath cannot contain repeated airports.")
        if self.t_min_minutes <= 0:
            raise DomainError("VALIDATION_ERROR", "t_min_minutes must be positive.")
