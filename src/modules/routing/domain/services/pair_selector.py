from collections.abc import Sequence

from src.modules.routing.domain.model.aggregates.airport_graph import AirportGraph
from src.modules.routing.domain.model.value_objects.iata_code import IataCode
from src.modules.routing.domain.model.value_objects.pair_reachability import (
    PairReachability,
)
from src.modules.routing.domain.services.a_star_search import AStarSearch
from src.modules.routing.domain.services.breadth_first_search import BreadthFirstSearch


class PairSelector:
    def __init__(
        self,
        bfs: BreadthFirstSearch | None = None,
        astar: AStarSearch | None = None,
    ) -> None:
        self._bfs = bfs or BreadthFirstSearch()
        self._astar = astar or AStarSearch()

    def select(
        self,
        graph: AirportGraph,
        origins: Sequence[IataCode],
        destinations: Sequence[IataCode],
        round_trip: bool,
        limit: int = 2,
    ) -> list[PairReachability]:
        candidates: list[PairReachability] = []

        for orig in origins:
            for dest in destinations:
                if orig == dest:
                    continue
                bfs_out = self._bfs.min_stops(graph, orig, dest)
                if not bfs_out.reachable or bfs_out.min_stops is None:
                    continue

                if round_trip:
                    bfs_in = self._bfs.min_stops(graph, dest, orig)
                    if not bfs_in.reachable or bfs_in.min_stops is None:
                        continue
                    path_out = self._astar.fastest_path(graph, orig, dest)
                    path_in = self._astar.fastest_path(graph, dest, orig)
                    if path_out is None or path_in is None:
                        continue
                    total_stops = bfs_out.min_stops + bfs_in.min_stops
                    total_t_min = path_out.t_min_minutes + path_in.t_min_minutes
                    candidates.append(
                        PairReachability(
                            origin=orig,
                            destination=dest,
                            reachable=True,
                            min_stops=total_stops,
                            t_min_minutes=total_t_min,
                            path=path_out,
                        )
                    )
                else:
                    path_out = self._astar.fastest_path(graph, orig, dest)
                    if path_out is None:
                        continue
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
                -(graph.out_degree.get(p.origin, 0) + graph.out_degree.get(p.destination, 0)),
                p.t_min_minutes,
                p.origin,
                p.destination,
            )
        )
        return candidates[:limit]
