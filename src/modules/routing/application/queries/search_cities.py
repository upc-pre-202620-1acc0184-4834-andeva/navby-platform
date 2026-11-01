from dataclasses import dataclass

from src.modules.routing.domain.model.aggregates.airport_graph import AirportGraph
from src.modules.routing.domain.model.value_objects.city import City
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result


@dataclass(frozen=True, slots=True)
class SearchCitiesQuery:
    q: str
    limit: int = 10


class SearchCitiesHandler:
    def __init__(self, graph: AirportGraph) -> None:
        self._graph = graph

    def handle(self, query: SearchCitiesQuery) -> Result[list[City]]:
        q_clean = query.q.strip()
        if len(q_clean) < 2:
            return Result.failure(
                ApplicationError(
                    code="VALIDATION_ERROR",
                    message="El texto de búsqueda debe tener al menos 2 caracteres.",
                    details={"invalid_params": [{"name": "q", "reason": "min_length is 2"}]},
                )
            )
        if not (1 <= query.limit <= 20):
            return Result.failure(
                ApplicationError(
                    code="VALIDATION_ERROR",
                    message="El límite debe estar entre 1 y 20.",
                    details={"invalid_params": [{"name": "limit", "reason": "must be <= 20"}]},
                )
            )
        cities = self._graph.search_cities(q_clean, limit=query.limit)
        return Result.success(cities)
