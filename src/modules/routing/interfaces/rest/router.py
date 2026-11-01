from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from src.modules.routing.application.queries.preview_route import (
    PreviewRouteHandler,
    PreviewRouteQuery,
)
from src.modules.routing.application.queries.search_cities import (
    SearchCitiesHandler,
    SearchCitiesQuery,
)
from src.modules.routing.domain.model.aggregates.airport_graph import AirportGraph
from src.modules.routing.infrastructure.persistence.graph_provider import get_airport_graph
from src.modules.routing.interfaces.rest.assemblers import (
    assemble_cities_response,
    assemble_preview_response,
)
from src.modules.routing.interfaces.rest.schemas import (
    CitiesResponse,
    RoutePreviewResponse,
)
from src.shared.interfaces.http_errors import to_http
from src.shared.interfaces.problem_details import ProblemDetails
from src.shared.interfaces.rate_limit import client_ip_key, rate_limit

routing_router = APIRouter(prefix="/api/v1/routing", tags=["Routing"])


@routing_router.get(
    "/cities",
    response_model=CitiesResponse,
    responses={422: {"model": ProblemDetails}},
)
async def get_cities(
    request: Request,
    graph: Annotated[AirportGraph, Depends(get_airport_graph)],
    q: Annotated[str, Query(description="Texto de búsqueda (≥ 2 caracteres)")],
    limit: Annotated[int, Query(description="Máximo de resultados (≤ 20)")] = 10,
) -> CitiesResponse:
    handler = SearchCitiesHandler(graph)
    res = handler.handle(SearchCitiesQuery(q=q, limit=limit))
    if not res.is_success:
        raise to_http(res, request)
    return assemble_cities_response(res.value)


@routing_router.get(
    "/preview",
    response_model=RoutePreviewResponse,
    dependencies=[Depends(rate_limit("routing_preview", client_ip_key, 30))],
    responses={
        404: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
        429: {"model": ProblemDetails},
    },
)
async def get_route_preview(
    request: Request,
    graph: Annotated[AirportGraph, Depends(get_airport_graph)],
    origins: Annotated[str, Query(description="Códigos IATA separados por coma (1-5)")],
    destinations: Annotated[str, Query(description="Códigos IATA separados por coma (1-5)")],
    trip_type: Annotated[str, Query(description="ONE_WAY o ROUND_TRIP")] = "ONE_WAY",
) -> RoutePreviewResponse:
    origin_list = [x.strip() for x in origins.split(",") if x.strip()]
    dest_list = [x.strip() for x in destinations.split(",") if x.strip()]
    handler = PreviewRouteHandler(graph)
    res = handler.handle(
        PreviewRouteQuery(
            origins=origin_list,
            destinations=dest_list,
            trip_type=trip_type,
        )
    )
    if not res.is_success:
        raise to_http(res, request)
    return assemble_preview_response(res.value, graph)
