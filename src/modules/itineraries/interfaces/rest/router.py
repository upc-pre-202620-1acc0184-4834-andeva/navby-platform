from datetime import date, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict

from src.modules.itineraries.application.commands.delete_itinerary import (
    DeleteItineraryCommand,
    DeleteItineraryHandler,
)
from src.modules.itineraries.application.commands.save_itinerary import (
    SaveItineraryCommand,
    SaveItineraryHandler,
)
from src.modules.itineraries.application.queries.get_itinerary import (
    GetItineraryHandler,
    GetItineraryQuery,
)
from src.modules.itineraries.application.queries.list_itineraries import (
    ListItinerariesHandler,
    ListItinerariesQuery,
)
from src.modules.itineraries.domain.model.aggregates.saved_itinerary import (
    SavedItinerary,
)
from src.modules.itineraries.infrastructure.persistence.sqlalchemy_saved_itinerary_repository import (  # noqa: E501
    SqlAlchemySavedItineraryRepository,
)
from src.modules.quotes.infrastructure.cache.redis_search_session_store import (
    RedisSearchSessionStore,
)
from src.modules.quotes.interfaces.acl.facade.quotes_facade import QuotesFacade
from src.modules.routing.domain.model.aggregates.airport_graph import AirportGraph
from src.modules.routing.infrastructure.persistence.graph_provider import (
    get_airport_graph,
)
from src.modules.routing.interfaces.acl.facade.routing_facade import RoutingFacade
from src.shared.application.current_user import CurrentUser
from src.shared.infrastructure.database import get_session_factory
from src.shared.infrastructure.redis_client import get_redis_client
from src.shared.infrastructure.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from src.shared.interfaces.auth import get_current_user
from src.shared.interfaces.http_errors import raise_for_error
from src.shared.interfaces.page import Page
from src.shared.interfaces.problem_details import ProblemDetails

router = APIRouter(tags=["itineraries"])


class SaveItineraryRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "search_id": "srch_01933c9a7f1870008000000000000001",
                "offer_id": "off_1",
                "name": "Viaje Lima - Madrid 2026",
            }
        },
    )

    search_id: str
    offer_id: str
    name: str | None = None


class ItineraryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    trip_type: str
    origin: str
    destination: str
    departure_date: date
    return_date: date | None
    price_disclaimer: str
    offer: dict[str, Any]
    created_at: datetime


def _to_response(itinerary: SavedItinerary) -> ItineraryResponse:
    quoted_str = itinerary.offer.quoted_at.strftime("%Y-%m-%d")
    return ItineraryResponse(
        id=itinerary.id,
        name=itinerary.name.value,
        trip_type=itinerary.trip_type,
        origin=itinerary.origin,
        destination=itinerary.destination,
        departure_date=itinerary.departure_date,
        return_date=itinerary.return_date,
        price_disclaimer=f"Precio del {quoted_str}; puede haber cambiado.",
        offer=itinerary.offer.data,
        created_at=itinerary.created_at,
    )


def get_quotes_facade(
    graph: Annotated[AirportGraph, Depends(get_airport_graph)],
) -> QuotesFacade:
    return QuotesFacade(
        session_store=RedisSearchSessionStore(get_redis_client()),
        routing_facade=RoutingFacade(graph=graph),
    )


@router.post(
    "/itineraries",
    summary="Guardar un vuelo del podio en la colección de itinerarios del usuario",
    description=(
        "Toma una oferta (`offer_id`) perteneciente a una sesión activa de cotización "
        "(`search_id`) y "
        "persiste una instantánea completa (`OfferSnapshot` JSONB) en PostgreSQL.\n\n"
        "- **Idempotente:** si el mismo `(search_id, offer_id)` ya fue guardado por el "
        "usuario, devuelve `200 OK` con el itinerario existente; si es nuevo, devuelve `201 "
        "Created`.\n"
        "- **Límite por usuario:** máximo 20 itinerarios guardados (`409 "
        "ITINERARY_LIMIT_REACHED`).\n"
        '- Si `name` se omite o viene vacío, asigna automáticamente `"{origin} → '
        '{destination} ({departure_date})"`.\n'
        "- 🔒 **Requiere autenticación:** `Authorization: Bearer <access_token>`."
    ),
    response_model=ItineraryResponse,
    responses={
        201: {"model": ItineraryResponse},
        401: {"model": ProblemDetails},
        404: {"model": ProblemDetails},
        409: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
    },
)
async def save_itinerary(
    body: SaveItineraryRequest,
    response: Response,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    quotes_facade: Annotated[QuotesFacade, Depends(get_quotes_facade)],
) -> ItineraryResponse:
    uow = SqlAlchemyUnitOfWork(get_session_factory())
    repo = SqlAlchemySavedItineraryRepository(uow)
    handler = SaveItineraryHandler(
        repo=repo,
        quotes_facade=quotes_facade,
        uow=uow,
    )
    res = await handler.handle(
        SaveItineraryCommand(
            user_id=current_user.user_id,
            search_id=body.search_id,
            offer_id=body.offer_id,
            name=body.name,
        )
    )
    if res.is_failure:
        raise_for_error(res.error)
    response.status_code = status.HTTP_201_CREATED if res.value.created else status.HTTP_200_OK
    return _to_response(res.value.itinerary)


@router.get(
    "/itineraries",
    summary="Listar itinerarios guardados por el usuario",
    description=(
        "Devuelve la lista paginada de itinerarios guardados por el usuario autenticado, ordenados "
        "del más reciente al más antiguo (`created_at DESC`).\n\n"
        "- 🔒 **Requiere autenticación:** `Authorization: Bearer <access_token>`."
    ),
    response_model=Page[ItineraryResponse],
    responses={
        401: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
    },
)
async def list_itineraries(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    page: int = Query(default=1, description="Número de página (≥ 1)."),
    page_size: int = Query(default=20, description="Tamaño de página (1 a 100)."),
) -> Page[ItineraryResponse]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = SqlAlchemySavedItineraryRepository(session)
        handler = ListItinerariesHandler(repo=repo)
        res = await handler.handle(
            ListItinerariesQuery(
                user_id=current_user.user_id,
                page=page,
                page_size=page_size,
            )
        )
    if res.is_failure:
        raise_for_error(res.error)
    return Page(
        items=[_to_response(item) for item in res.value.items],
        page=res.value.page,
        page_size=res.value.page_size,
        total=res.value.total,
    )


@router.get(
    "/itineraries/{itinerary_id}",
    summary="Obtener el detalle completo de un itinerario guardado",
    description=(
        "Recupera un itinerario guardado por su UUID incluyendo el snapshot completo del "
        "vuelo (`offer`), "
        "tramos, aerolíneas, coordenadas de aeropuertos y `price_disclaimer`.\n\n"
        "- 🔒 **Requiere autenticación del propietario (`404 ITINERARY_NOT_FOUND` si no "
        "existe o pertenece a otro usuario).**"
    ),
    response_model=ItineraryResponse,
    responses={
        401: {"model": ProblemDetails},
        404: {"model": ProblemDetails},
    },
)
async def get_itinerary(
    itinerary_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ItineraryResponse:
    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = SqlAlchemySavedItineraryRepository(session)
        handler = GetItineraryHandler(repo=repo)
        res = await handler.handle(
            GetItineraryQuery(
                user_id=current_user.user_id,
                itinerary_id=itinerary_id,
            )
        )
    if res.is_failure:
        raise_for_error(res.error)
    return _to_response(res.value)


@router.delete(
    "/itineraries/{itinerary_id}",
    summary="Eliminar un itinerario guardado",
    description=(
        "Borra permanentemente un itinerario de la colección del usuario autenticado y "
        "libera un espacio "
        "dentro de su límite de 20 itinerarios.\n\n"
        "- 🔒 **Requiere autenticación del propietario (`404 ITINERARY_NOT_FOUND` si no "
        "existe o pertenece a otro usuario).**"
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ProblemDetails},
        404: {"model": ProblemDetails},
    },
)
async def delete_itinerary(
    itinerary_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Response:
    uow = SqlAlchemyUnitOfWork(get_session_factory())
    repo = SqlAlchemySavedItineraryRepository(uow)
    handler = DeleteItineraryHandler(repo=repo, uow=uow)
    res = await handler.handle(
        DeleteItineraryCommand(
            user_id=current_user.user_id,
            itinerary_id=itinerary_id,
        )
    )
    if res.is_failure:
        raise_for_error(res.error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
