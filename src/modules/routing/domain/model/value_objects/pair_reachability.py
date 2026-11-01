from dataclasses import dataclass

from src.modules.routing.domain.model.value_objects.iata_code import IataCode
from src.modules.routing.domain.model.value_objects.route_path import RoutePath


@dataclass(frozen=True, slots=True)
class PairReachability:
    origin: IataCode
    destination: IataCode
    reachable: bool
    min_stops: int
    t_min_minutes: int
    path: RoutePath
