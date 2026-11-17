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
from src.shared.interfaces.auth import get_current_user
from src.shared.interfaces.http_errors import to_http
from src.shared.interfaces.problem_details import ProblemDetails
from src.shared.interfaces.rate_limit import rate_limit, user_id_key

routing_router = APIRouter(prefix="/api/v1/routing", tags=["Routing"])


@routing_router.get(
    "/cities",
    summary="Autocompletar ciudades y aeropuertos IATA",
    description=(
        "`q` necesita al menos 2 caracteres y coincide por prefijo con el nombre de la "
        "ciudad (en inglés o su alias en español), el nombre del aeropuerto o el código "
        "IATA. No distingue mayúsculas ni tildes. Devuelve cada ciudad con todos sus "
        "aeropuertos (RN-06).\n\n"
        "- 🔒 Requiere `Authorization: Bearer <access_token>`.\n"
        "- `limit` admite como máximo 20."
    ),
    response_model=CitiesResponse,
    dependencies=[Depends(get_current_user)],
    responses={
        401: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
    },
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
        "Evalúa todas las combinaciones de `origins` y `destinations` (1 a 5 "
        "aeropuertos por lado, sin aeropuertos en común) con **BFS** (¿hay ruta con 2 "
        "escalas o menos?, RN-05) y **A\\*** (ruta físicamente más rápida: 800 km/h, +30 "
        "min por tramo y +60 min por escala).\n\n"
        "- `pairs`: los pares que se cotizarían, como máximo 2 (RN-14).\n"
        "- `best_route`: la ruta de ida del par con menor T_min.\n"
        "- Con `trip_type=ROUND_TRIP`, `t_min_minutes` suma ida y vuelta.\n"
        "- Si ningún par tiene ruta: `200` con `reachable: false`.\n"
        "- 🔒 Requiere `Authorization: Bearer <access_token>`. **Rate limit:** 30 por "
        "minuto por usuario.\n"
        "- **Errores:** `401 UNAUTHENTICATED`, `404 AIRPORT_NOT_FOUND`, "
        "`422 VALIDATION_ERROR`."
    ),
    response_model=RoutePreviewResponse,
    dependencies=[
        Depends(get_current_user),
        Depends(rate_limit("routing_preview", user_id_key, 30)),
    ],
    responses={
        401: {"model": ProblemDetails},
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
