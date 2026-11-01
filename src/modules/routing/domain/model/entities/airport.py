from dataclasses import dataclass

from src.modules.routing.domain.model.value_objects.coordinates import Coordinates
from src.modules.routing.domain.model.value_objects.iata_code import IataCode


@dataclass(frozen=True, slots=True)
class Airport:
    iata: IataCode
    icao: str
    name: str
    city: str
    country: str
    coordinates: Coordinates
    timezone: str
