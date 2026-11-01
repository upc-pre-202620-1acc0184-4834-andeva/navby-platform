import time
from dataclasses import dataclass

from src.modules.routing.domain.model.aggregates.airport_graph import AirportGraph
from src.modules.routing.domain.model.value_objects.iata_code import IataCode
from src.modules.routing.domain.model.value_objects.pair_reachability import (
    PairReachability,
)
from src.modules.routing.domain.services.a_star_search import AStarSearch
from src.modules.routing.domain.services.breadth_first_search import BreadthFirstSearch
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.domain.domain_error import DomainError


@dataclass(frozen=True, slots=True)
class PreviewRouteQuery:
    origins: list[str]
    destinations: list[str]
    trip_type: str = "ONE_WAY"


@dataclass(frozen=True, slots=True)
class PreviewTelemetry:
    pairs_evaluated: int
    bfs_ms: float
    astar_ms: float
    astar_nodes_expanded: int


@dataclass(frozen=True, slots=True)
class PreviewRouteResult:
    reachable: bool
    pairs: list[PairReachability]
    best_pair: PairReachability | None
    telemetry: PreviewTelemetry


class PreviewRouteHandler:
    def __init__(
        self,
        graph: AirportGraph,
        bfs: BreadthFirstSearch | None = None,
        astar: AStarSearch | None = None,
    ) -> None:
        self._graph = graph
        self._bfs = bfs or BreadthFirstSearch()
        self._astar = astar or AStarSearch()

    def handle(self, query: PreviewRouteQuery) -> Result[PreviewRouteResult]:
        if query.trip_type not in ("ONE_WAY", "ROUND_TRIP"):
            return Result.failure(
                ApplicationError(
                    code="VALIDATION_ERROR",
                    message="trip_type debe ser ONE_WAY o ROUND_TRIP.",
                    details={"invalid_params": [{"name": "trip_type", "reason": "invalid enum"}]},
                )
            )
        if not (1 <= len(query.origins) <= 5) or not (1 <= len(query.destinations) <= 5):
            return Result.failure(
                ApplicationError(
                    code="VALIDATION_ERROR",
                    message="Se permiten entre 1 y 5 aeropuertos por origen y destino.",
                )
            )

        origin_codes: list[IataCode] = []
        dest_codes: list[IataCode] = []
        try:
            for raw in query.origins:
                origin_codes.append(IataCode(raw.strip().upper()))
            for raw in query.destinations:
                dest_codes.append(IataCode(raw.strip().upper()))
        except DomainError as exc:
            return Result.failure(ApplicationError(code=exc.code, message=exc.message))

        if set(origin_codes) & set(dest_codes):
            return Result.failure(
                ApplicationError(
                    code="VALIDATION_ERROR",
                    message="Origen y destino no pueden compartir aeropuertos.",
                )
            )

        for code in (*origin_codes, *dest_codes):
            if self._graph.airport(code) is None:
                return Result.failure(
                    ApplicationError(
                        code="AIRPORT_NOT_FOUND",
                        message=f"El aeropuerto {code.value} no existe en el grafo.",
                    )
                )

        round_trip = query.trip_type == "ROUND_TRIP"
        pairs_evaluated = 0
        bfs_seconds = 0.0
        astar_seconds = 0.0
        total_nodes_expanded = 0
        candidates: list[PairReachability] = []

        for orig in origin_codes:
            for dest in dest_codes:
                pairs_evaluated += 1
                t0 = time.perf_counter()
                bfs_out = self._bfs.min_stops(self._graph, orig, dest)
                bfs_in = (
                    self._bfs.min_stops(self._graph, dest, orig)
                    if (round_trip and bfs_out.reachable)
                    else None
                )
                bfs_seconds += time.perf_counter() - t0

                if not bfs_out.reachable or bfs_out.min_stops is None:
                    continue
                if round_trip and (
                    bfs_in is None or not bfs_in.reachable or bfs_in.min_stops is None
                ):
                    continue

                t1 = time.perf_counter()
                path_out = self._astar.fastest_path(self._graph, orig, dest)
                path_in = self._astar.fastest_path(self._graph, dest, orig) if round_trip else None
                astar_seconds += time.perf_counter() - t1

                if path_out is None:
                    continue
                total_nodes_expanded += path_out.nodes_expanded

                if round_trip:
                    if path_in is None or bfs_in is None or bfs_in.min_stops is None:
                        continue
                    total_nodes_expanded += path_in.nodes_expanded
                    candidates.append(
                        PairReachability(
                            origin=orig,
                            destination=dest,
                            reachable=True,
                            min_stops=bfs_out.min_stops + bfs_in.min_stops,
                            t_min_minutes=path_out.t_min_minutes + path_in.t_min_minutes,
                            path=path_out,
                        )
                    )
                else:
                    candidates.append(
                        PairReachability(
                            origin=orig,
                            destination=dest,
                            reachable=True,
                            min_stops=bfs_out.min_stops,
                            t_min_minutes=path_out.t_min_minutes,
                            path=path_out,
                        )
                    )

        candidates.sort(
            key=lambda p: (
                p.min_stops,
                -(
                    self._graph.out_degree.get(p.origin, 0)
                    + self._graph.out_degree.get(p.destination, 0)
                ),
                p.t_min_minutes,
                p.origin,
                p.destination,
            )
        )
        selected_pairs = candidates[:2]
        best_pair = min(selected_pairs, key=lambda p: p.t_min_minutes) if selected_pairs else None
        telemetry = PreviewTelemetry(
            pairs_evaluated=pairs_evaluated,
            bfs_ms=round(bfs_seconds * 1000.0, 3),
            astar_ms=round(astar_seconds * 1000.0, 3),
            astar_nodes_expanded=total_nodes_expanded,
        )
        return Result.success(
            PreviewRouteResult(
                reachable=bool(selected_pairs),
                pairs=selected_pairs,
                best_pair=best_pair,
                telemetry=telemetry,
            )
        )
