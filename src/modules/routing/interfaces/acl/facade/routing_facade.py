from dataclasses import dataclass

from src.modules.routing.domain.model.aggregates.airport_graph import AirportGraph
from src.modules.routing.domain.model.value_objects.iata_code import IataCode
from src.modules.routing.domain.services.pair_selector import PairSelector
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.domain.domain_error import DomainError


@dataclass(frozen=True, slots=True)
class PairReachabilityDTO:
    origin: str
    destination: str
    min_stops: int
    t_min_minutes: int
    route_airports: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AirportDTO:
    iata: str
    name: str
    city: str
    lat: float
    lon: float
    timezone: str


class RoutingFacade:
    def __init__(self, graph: AirportGraph, selector: PairSelector | None = None) -> None:
        self._graph = graph
        self._selector = selector or PairSelector()

    def select_pairs(
        self,
        origins: list[str],
        destinations: list[str],
        round_trip: bool,
    ) -> Result[list[PairReachabilityDTO]]:
        try:
            origin_codes = [IataCode(code) for code in origins]
            dest_codes = [IataCode(code) for code in destinations]
        except DomainError as exc:
            return Result.failure(ApplicationError(code=exc.code, message=exc.message))

        for code in (*origin_codes, *dest_codes):
            if self._graph.airport(code) is None:
                return Result.failure(
                    ApplicationError(
                        code="AIRPORT_NOT_FOUND",
                        message=f"El aeropuerto {code.value} no existe en el grafo.",
                    )
                )

        pairs = self._selector.select(
            self._graph,
            origins=origin_codes,
            destinations=dest_codes,
            round_trip=round_trip,
            limit=2,
        )
        dtos = [
            PairReachabilityDTO(
                origin=p.origin.value,
                destination=p.destination.value,
                min_stops=p.min_stops,
                t_min_minutes=p.t_min_minutes,
                route_airports=tuple(a.value for a in p.path.airports),
            )
            for p in pairs
        ]
        return Result.success(dtos)

    def get_airports(self, iatas: list[str]) -> list[AirportDTO]:
        result: list[AirportDTO] = []
        seen: set[str] = set()
        for raw in iatas:
            if raw in seen:
                continue
            seen.add(raw)
            try:
                code = IataCode(raw)
            except DomainError:
                continue
            ap = self._graph.airport(code)
            if ap is not None:
                result.append(
                    AirportDTO(
                        iata=ap.iata.value,
                        name=ap.name,
                        city=ap.city,
                        lat=ap.coordinates.lat,
                        lon=ap.coordinates.lon,
                        timezone=ap.timezone,
                    )
                )
        return result
