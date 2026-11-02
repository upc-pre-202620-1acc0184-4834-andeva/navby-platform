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
    summary="Autocompletar ciudades y aeropuertos IATA",
    description=(
        "Busca ciudades y aeropuertos en el grafo en memoria de OpenFlights (`3,354` "
        "aeropuertos con código IATA).\n\n"
        '- Soporta búsqueda insensible a mayúsculas y tildes (`"cusco"`, `"nueva york"`, '
        '`"londres"`), '
        "alias en español (`data/city_aliases_es.json`) y coincidencia directa por código "
        'IATA (`"LIM"`, `"MAD"`).\n'
        "- Agrupa aeropuertos metropolitanos bajo su ciudad principal y devuelve coordenadas "
        "geográficas (`lat`, `lon`).\n"
        "- **Gratuito (`RN-03`):** no requiere autenticación ni consume créditos."
    ),
    response_model=CitiesResponse,
    responses={422: {"model": ProblemDetails}},
)
async def get_cities(
    request: Request,
    graph: Annotated[AirportGraph, Depends(get_airport_graph)],
    q: Annotated[
        str,
        Query(
            description="Texto de búsqueda (≥ 2 caracteres): ciudad, alias en español o IATA.",
            examples=["lima", "nueva york", "MAD"],
        ),
    ],
    limit: Annotated[int, Query(description="Máximo de resultados a devolver (1 a 20).")] = 10,
) -> CitiesResponse:
    handler = SearchCitiesHandler(graph)
    res = handler.handle(SearchCitiesQuery(q=q, limit=limit))
    if not res.is_success:
        raise to_http(res, request)
    return assemble_cities_response(res.value)


@routing_router.get(
    "/preview",
    summary="Previsualizar conectividad aérea y tiempo mínimo físico (BFS + A*)",
    description=(
        "Verifica instantáneamente en el grafo en memoria si existe ruta aérea entre el "
        "conjunto de orígenes "
        "y destinos (`1` a `5` códigos IATA por lado, `RN-01`) antes de gastar créditos en "
        "FlightAPI (`RN-05`).\n\n"
        "- **Algoritmo 1 — BFS (*Breadth-First Search*):** halla el camino con el **menor "
        "número de escalas** (`min_stops_path`).\n"
        "- **Algoritmo 2 — A\\* (*A-Star* con heurística admisible Haversine a $900\\text{ "
        "km/h}$):** halla el camino de "
        "**tiempo mínimo físico** $T_{\\min}$ (`fastest_path`, incluyendo $45\\text{ min}$ por "
        "escala interna y $35\\text{ min}$ fijos de rodaje/despegue).\n"
        "- Ordena hasta los 4 mejores pares `(origin, destination)` candidatos para cotizar.\n"
        "- **Gratuito (`RN-05`):** no consume créditos (rate limit: 30 req/min por IP)."
    ),
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
    origins: Annotated[
        str,
        Query(
            description="Códigos IATA de origen separados por coma (1 a 5 aeropuertos).",
            examples=["LIM"],
        ),
    ],
    destinations: Annotated[
        str,
        Query(
            description="Códigos IATA de destino separados por coma (1 a 5 aeropuertos).",
            examples=["MAD"],
        ),
    ],
    trip_type: Annotated[
        str,
        Query(
            description="Tipo de viaje: ONE_WAY (solo ida) o ROUND_TRIP (ida y vuelta).",
            examples=["ONE_WAY", "ROUND_TRIP"],
        ),
    ] = "ONE_WAY",
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
