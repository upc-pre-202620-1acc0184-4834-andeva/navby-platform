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
    model_config = ConfigDict(extra="forbid")

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
    response_model=Page[ItineraryResponse],
    responses={
        401: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
    },
)
async def list_itineraries(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    page: int = Query(default=1),
    page_size: int = Query(default=20),
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
