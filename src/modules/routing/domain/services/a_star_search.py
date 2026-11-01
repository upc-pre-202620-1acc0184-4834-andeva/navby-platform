import heapq

from src.modules.routing.domain.model.aggregates.airport_graph import AirportGraph
from src.modules.routing.domain.model.value_objects.iata_code import IataCode
from src.modules.routing.domain.model.value_objects.route_path import RoutePath
from src.modules.routing.domain.services.haversine import Haversine


class AStarSearch:
    STOP_PENALTY_MINUTES = 60.0
    CRUISE_SPEED_KMH = 800.0

    def fastest_path(
        self,
        graph: AirportGraph,
        origin: IataCode,
        destination: IataCode,
        max_legs: int = 3,
    ) -> RoutePath | None:
        orig_airport = graph.airport(origin)
        dest_airport = graph.airport(destination)
        if orig_airport is None or dest_airport is None or origin == destination:
            return None

        dest_coords = dest_airport.coordinates

        def heuristic(code: IataCode) -> float:
            if code == destination:
                return 0.0
            ap = graph.airport(code)
            if ap is None:
                return 0.0
            dist_km = Haversine.distance_km(ap.coordinates, dest_coords)
            return (dist_km / self.CRUISE_SPEED_KMH) * 60.0

        h0 = heuristic(origin)
        heap: list[tuple[float, float, int, IataCode, tuple[IataCode, ...]]] = [
            (h0, 0.0, 0, origin, (origin,))
        ]
        best_g: dict[tuple[IataCode, int], float] = {(origin, 0): 0.0}
        nodes_expanded = 0

        while heap:
            _f, g, legs_used, current, path = heapq.heappop(heap)
            if current == destination:
                return RoutePath(
                    airports=path,
                    t_min_minutes=round(g),
                    nodes_expanded=nodes_expanded,
                )

            if g > best_g.get((current, legs_used), float("inf")):
                continue

            if legs_used >= max_legs:
                continue

            nodes_expanded += 1
            penalty = 0.0 if current == origin else self.STOP_PENALTY_MINUTES
            next_legs = legs_used + 1

            for edge in graph.neighbors(current):
                nxt = edge.to
                if nxt in path:
                    continue
                if next_legs == max_legs and nxt != destination:
                    continue
                new_g = g + penalty + edge.minutes
                state = (nxt, next_legs)
                if new_g < best_g.get(state, float("inf")):
                    best_g[state] = new_g
                    new_f = new_g + heuristic(nxt)
                    heapq.heappush(heap, (new_f, new_g, next_legs, nxt, (*path, nxt)))

        return None
