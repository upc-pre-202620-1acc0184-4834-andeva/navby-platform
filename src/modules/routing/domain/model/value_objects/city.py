from dataclasses import dataclass

from src.modules.routing.domain.model.entities.airport import Airport


@dataclass(frozen=True, slots=True)
class City:
    city: str
    city_es: str | None
    country: str
    airports: tuple[Airport, ...]
