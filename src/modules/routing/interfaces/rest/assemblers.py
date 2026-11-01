from src.modules.routing.application.queries.preview_route import PreviewRouteResult
from src.modules.routing.domain.model.aggregates.airport_graph import AirportGraph
from src.modules.routing.domain.model.value_objects.city import City
from src.modules.routing.interfaces.rest.schemas import (
    BestRouteSchema,
    CitiesResponse,
    CityAirportSchema,
    CitySchema,
    PreviewPairSchema,
    PreviewTelemetrySchema,
    RouteAirportPointSchema,
    RoutePreviewResponse,
)


def assemble_cities_response(cities: list[City]) -> CitiesResponse:
    return CitiesResponse(
        cities=[
            CitySchema(
                city=c.city,
                city_es=c.city_es,
                country=c.country,
                airports=[
                    CityAirportSchema(
                        iata=a.iata.value,
                        name=a.name,
                        lat=a.coordinates.lat,
                        lon=a.coordinates.lon,
                    )
                    for a in c.airports
                ],
            )
            for c in cities
        ]
    )


def assemble_preview_response(
    result: PreviewRouteResult,
    graph: AirportGraph,
) -> RoutePreviewResponse:
    best_route: BestRouteSchema | None = None
    if result.best_pair is not None:
        points: list[RouteAirportPointSchema] = []
        for iata in result.best_pair.path.airports:
            ap = graph.airport(iata)
            if ap is not None:
                points.append(
                    RouteAirportPointSchema(
                        iata=ap.iata.value,
                        lat=ap.coordinates.lat,
                        lon=ap.coordinates.lon,
                    )
                )
        best_route = BestRouteSchema(
            t_min_minutes=result.best_pair.path.t_min_minutes,
            airports=points,
        )

    return RoutePreviewResponse(
        reachable=result.reachable,
        pairs=[
            PreviewPairSchema(
                origin=p.origin.value,
                destination=p.destination.value,
                min_stops=p.min_stops,
                t_min_minutes=p.t_min_minutes,
            )
            for p in result.pairs
        ],
        best_route=best_route,
        telemetry=PreviewTelemetrySchema(
            pairs_evaluated=result.telemetry.pairs_evaluated,
            bfs_ms=result.telemetry.bfs_ms,
            astar_ms=result.telemetry.astar_ms,
            astar_nodes_expanded=result.telemetry.astar_nodes_expanded,
        ),
    )
