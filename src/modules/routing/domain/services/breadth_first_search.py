from collections import deque

from src.modules.routing.domain.model.aggregates.airport_graph import AirportGraph
from src.modules.routing.domain.model.value_objects.iata_code import IataCode
from src.modules.routing.domain.model.value_objects.reachability_result import (
    ReachabilityResult,
)


class BreadthFirstSearch:
    def min_stops(
        self,
        graph: AirportGraph,
        origin: IataCode,
        destination: IataCode,
        max_legs: int = 3,
    ) -> ReachabilityResult:
        if (
            origin == destination
            or origin not in graph.airports
            or destination not in graph.airports
        ):
            return ReachabilityResult(reachable=False, min_stops=None)

        visited: set[IataCode] = {origin}
        queue: deque[tuple[IataCode, int]] = deque([(origin, 0)])

        while queue:
            current, legs_used = queue.popleft()
            if legs_used >= max_legs:
                continue
            next_legs = legs_used + 1
            for edge in graph.neighbors(current):
                neighbor = edge.to
                if neighbor == destination:
                    return ReachabilityResult(reachable=True, min_stops=next_legs - 1)
                if neighbor not in visited and next_legs < max_legs:
                    visited.add(neighbor)
                    queue.append((neighbor, next_legs))

        return ReachabilityResult(reachable=False, min_stops=None)
