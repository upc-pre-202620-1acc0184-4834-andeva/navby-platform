from typing import Annotated

from fastapi import APIRouter, Depends

from src.modules.billing.interfaces.acl.facade.billing_facade import BillingFacade
from src.modules.quotes.application.acl.ports.flight_offers_provider import (
    FlightOffersProvider,
)
from src.modules.quotes.application.acl.ports.offer_cache import OfferCache
from src.modules.quotes.application.acl.ports.provider_gate import ProviderGate
from src.modules.quotes.application.acl.ports.search_lock import SearchLock
from src.modules.quotes.application.acl.ports.search_session_store import (
    SearchSessionStore,
)
from src.modules.quotes.application.commands.rerank_quotes import (
    RerankQuotesCommand,
    RerankQuotesHandler,
)
from src.modules.quotes.application.commands.search_quotes import (
    SearchQuotesCommand,
    SearchQuotesHandler,
)
from src.modules.quotes.application.queries.get_quote_search import (
    GetQuoteSearchHandler,
    GetQuoteSearchQuery,
)
from src.modules.quotes.infrastructure.adapters.flight_api_offers_provider import (
    FlightApiOffersProvider,
)
from src.modules.quotes.infrastructure.adapters.in_memory_provider_gate import (
    InMemoryProviderGate,
)
from src.modules.quotes.infrastructure.adapters.mock_flight_offers_provider import (
    MockFlightOffersProvider,
)
from src.modules.quotes.infrastructure.cache.redis_offer_cache import RedisOfferCache
from src.modules.quotes.infrastructure.cache.redis_search_lock import RedisSearchLock
from src.modules.quotes.infrastructure.cache.redis_search_session_store import (
    RedisSearchSessionStore,
)
from src.modules.quotes.interfaces.rest.assemblers import to_podium_response
from src.modules.quotes.interfaces.rest.schemas import (
    PodiumResponse,
    RerankQuotesRequest,
    SearchQuotesRequest,
)
from src.modules.routing.domain.model.aggregates.airport_graph import AirportGraph
from src.modules.routing.infrastructure.persistence.graph_provider import (
    get_airport_graph,
)
from src.modules.routing.interfaces.acl.facade.routing_facade import RoutingFacade
from src.shared.application.current_user import CurrentUser
from src.shared.infrastructure.database import get_session_factory
from src.shared.infrastructure.redis_client import get_redis_client
from src.shared.infrastructure.settings import Settings, get_settings
from src.shared.interfaces.auth import get_verified_user
from src.shared.interfaces.http_errors import raise_for_error
from src.shared.interfaces.problem_details import ProblemDetails
from src.shared.interfaces.rate_limit import rate_limit, user_id_key

router = APIRouter(tags=["quotes"])

_provider_gate: ProviderGate | None = None


def get_provider_gate(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProviderGate:
    global _provider_gate
    if _provider_gate is None:
        _provider_gate = InMemoryProviderGate(max_concurrency=settings.flight_api_max_concurrency)
    return _provider_gate


def get_flight_offers_provider(
    settings: Annotated[Settings, Depends(get_settings)],
    gate: Annotated[ProviderGate, Depends(get_provider_gate)],
) -> FlightOffersProvider:
    if not settings.flight_api_key:
        return MockFlightOffersProvider()
    return FlightApiOffersProvider(api_key=settings.flight_api_key, gate=gate)


def get_offer_cache() -> OfferCache:
    return RedisOfferCache(get_redis_client())


def get_session_store() -> SearchSessionStore:
    return RedisSearchSessionStore(get_redis_client())


def get_search_lock() -> SearchLock:
    return RedisSearchLock(get_redis_client())


def get_routing_facade(
    graph: Annotated[AirportGraph, Depends(get_airport_graph)],
) -> RoutingFacade:
    return RoutingFacade(graph=graph)


def get_billing_facade() -> BillingFacade:
    return BillingFacade(get_session_factory())


@router.post(
    "/quotes/search",
    response_model=PodiumResponse,
    dependencies=[
        Depends(get_verified_user),
        Depends(rate_limit("quotes_search", user_id_key, 10)),
    ],
    responses={
        401: {"model": ProblemDetails},
        402: {"model": ProblemDetails},
        403: {"model": ProblemDetails},
        409: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
        429: {"model": ProblemDetails},
        503: {"model": ProblemDetails},
    },
)
async def search_quotes(
    body: SearchQuotesRequest,
    current_user: Annotated[CurrentUser, Depends(get_verified_user)],
    routing_facade: Annotated[RoutingFacade, Depends(get_routing_facade)],
    billing_facade: Annotated[BillingFacade, Depends(get_billing_facade)],
    offer_cache: Annotated[OfferCache, Depends(get_offer_cache)],
    session_store: Annotated[SearchSessionStore, Depends(get_session_store)],
    search_lock: Annotated[SearchLock, Depends(get_search_lock)],
    offers_provider: Annotated[FlightOffersProvider, Depends(get_flight_offers_provider)],
) -> PodiumResponse:
    prefs = body.preferences
    profile_str = prefs.profile if prefs is not None else "BALANCED"
    w_in = prefs.weights if prefs is not None else None

    handler = SearchQuotesHandler(
        routing_facade=routing_facade,
        billing_facade=billing_facade,
        offer_cache=offer_cache,
        session_store=session_store,
        search_lock=search_lock,
        offers_provider=offers_provider,
    )
    res = await handler.handle(
        SearchQuotesCommand(
            user_id=current_user.user_id,
            trip_type=body.trip_type,
            origins=body.origins,
            destinations=body.destinations,
            departure_date=body.departure_date,
            return_date=body.return_date,
            adults=body.passengers.adults,
            children=body.passengers.children,
            infants=body.passengers.infants,
            cabin=body.cabin,
            currency=body.currency,
            profile=profile_str,
            price_weight=w_in.price if w_in is not None else None,
            duration_weight=w_in.duration if w_in is not None else None,
            stops_weight=w_in.stops if w_in is not None else None,
        )
    )
    if res.is_failure:
        raise_for_error(res.error)
    return to_podium_response(res.value, routing_facade)


@router.post(
    "/quotes/{search_id}/rank",
    response_model=PodiumResponse,
    responses={
        401: {"model": ProblemDetails},
        403: {"model": ProblemDetails},
        404: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
    },
)
async def rerank_quotes(
    search_id: str,
    body: RerankQuotesRequest,
    current_user: Annotated[CurrentUser, Depends(get_verified_user)],
    routing_facade: Annotated[RoutingFacade, Depends(get_routing_facade)],
    session_store: Annotated[SearchSessionStore, Depends(get_session_store)],
) -> PodiumResponse:
    w_in = body.weights
    handler = RerankQuotesHandler(session_store=session_store)
    res = await handler.handle(
        RerankQuotesCommand(
            user_id=current_user.user_id,
            search_id=search_id,
            profile=body.profile,
            price_weight=w_in.price if w_in is not None else None,
            duration_weight=w_in.duration if w_in is not None else None,
            stops_weight=w_in.stops if w_in is not None else None,
        )
    )
    if res.is_failure:
        raise_for_error(res.error)
    return to_podium_response(res.value, routing_facade)


@router.get(
    "/quotes/{search_id}",
    response_model=PodiumResponse,
    responses={
        401: {"model": ProblemDetails},
        403: {"model": ProblemDetails},
        404: {"model": ProblemDetails},
    },
)
async def get_quote_search(
    search_id: str,
    current_user: Annotated[CurrentUser, Depends(get_verified_user)],
    routing_facade: Annotated[RoutingFacade, Depends(get_routing_facade)],
    session_store: Annotated[SearchSessionStore, Depends(get_session_store)],
) -> PodiumResponse:
    handler = GetQuoteSearchHandler(session_store=session_store)
    res = await handler.handle(
        GetQuoteSearchQuery(user_id=current_user.user_id, search_id=search_id)
    )
    if res.is_failure:
        raise_for_error(res.error)
    return to_podium_response(res.value, routing_facade)
