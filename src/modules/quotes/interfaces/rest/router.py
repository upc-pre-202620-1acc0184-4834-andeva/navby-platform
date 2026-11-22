from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from src.modules.billing.interfaces.acl.facade.billing_facade import BillingFacade
from src.modules.quotes.application.acl.ports.exchange_rate_cache import (
    ExchangeRateCache,
)
from src.modules.quotes.application.acl.ports.exchange_rate_provider import (
    ExchangeRateProvider,
)
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
from src.modules.quotes.application.queries.get_exchange_rates import (
    GetExchangeRatesHandler,
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
from src.modules.quotes.infrastructure.adapters.open_er_api_exchange_rate_provider import (
    OpenErApiExchangeRateProvider,
)
from src.modules.quotes.infrastructure.cache.redis_exchange_rate_cache import (
    RedisExchangeRateCache,
)
from src.modules.quotes.infrastructure.cache.redis_offer_cache import RedisOfferCache
from src.modules.quotes.infrastructure.cache.redis_search_lock import RedisSearchLock
from src.modules.quotes.infrastructure.cache.redis_search_session_store import (
    RedisSearchSessionStore,
)
from src.modules.quotes.interfaces.rest.assemblers import (
    to_exchange_rates_response,
    to_podium_response,
)
from src.modules.quotes.interfaces.rest.schemas import (
    ExchangeRatesResponse,
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
from src.shared.interfaces.rate_limit import client_ip_key, rate_limit, user_id_key

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


def get_exchange_rate_provider() -> ExchangeRateProvider:
    return OpenErApiExchangeRateProvider()


def get_exchange_rate_cache() -> ExchangeRateCache:
    return RedisExchangeRateCache(get_redis_client())


def get_routing_facade(
    graph: Annotated[AirportGraph, Depends(get_airport_graph)],
) -> RoutingFacade:
    return RoutingFacade(graph=graph)


def get_billing_facade() -> BillingFacade:
    return BillingFacade(get_session_factory())


@router.post(
    "/quotes/search",
    summary="Cotizar vuelos y calcular el podio multicriterio (Top 3 sobre Frontera de Pareto)",
    description=(
        "Cotiza ofertas reales y devuelve el **podio**: las 3 mejores según un único "
        "puntaje que combina precio, duración y escalas.\n\n"
        "1. BFS y A\\* descartan los pares sin ruta y eligen como máximo los 2 mejores "
        "(RN-07, RN-14).\n"
        "2. Cada par se busca en la caché de 30 minutos (RN-10).\n"
        "3. Si algún par no está en caché se debitan **5 créditos** antes de llamar a "
        "FlightAPI; si todos están en caché, la búsqueda cuesta 0 (RN-08).\n"
        "4. Los créditos se reembolsan si todas las llamadas fallan o si no hay vuelos "
        "(RN-09).\n"
        "5. Motor multicriterio: frontera de Pareto, normalización min-max sobre las "
        "ofertas reales y distancia euclidiana ponderada al punto ideal.\n\n"
        "- **Perfiles** (precio, duración, escalas): `BALANCED` (0.5, 0.3, 0.2), "
        "`SAVER` (0.7, 0.2, 0.1), `FAST` (0.2, 0.6, 0.2) o `CUSTOM` con `weights` que "
        "sumen 1.\n"
        "- Solo una cotización en curso por usuario (RN-15). **Rate limit:** 10 por "
        "minuto por usuario.\n"
        "- 🔒 Requiere `Authorization: Bearer <access_token>` de un usuario con correo "
        "verificado.\n"
        "- **Errores:** `402 INSUFFICIENT_CREDITS`, `403 EMAIL_NOT_VERIFIED`, `409 "
        "SEARCH_IN_PROGRESS`, `422 ROUTE_NOT_REACHABLE`, `422 INVALID_WEIGHTS`, `503 "
        "PROVIDER_UNAVAILABLE`."
    ),
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
    summary="Reordenar el podio en tiempo real con otro perfil o pesos personalizados (0 créditos)",
    description=(
        "Reordena la frontera de Pareto ya cotizada con otro perfil (`BALANCED`, "
        "`SAVER`, `FAST`) o con `CUSTOM` y sus `weights`. No llama a FlightAPI, "
        "devuelve `credits_charged: 0` y conserva la misma `expires_at` (RN-11).\n\n"
        "- 🔒 Requiere `Authorization: Bearer <access_token>` de un usuario con correo "
        "verificado.\n"
        "- **Errores:** `404 SEARCH_NOT_FOUND`, `422 INVALID_WEIGHTS`."
    ),
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
    "/fx/rates",
    summary="Tipo de cambio para mostrar precios en la moneda local",
    description=(
        "Unidades de `USD` y `PEN` por 1 USD. Las cotizaciones siempre llegan en `USD`; la "
        "webapp convierte al mostrar. El valor se guarda 6 horas en Redis; si el proveedor "
        "(open.er-api.com) no responde se devuelve un valor de respaldo con "
        '`source: "fallback"`.\n\n'
        "- Público, sin autenticación. **Rate limit:** 60 por minuto por IP.\n"
        "- Respuesta con `Cache-Control: public, max-age=3600`."
    ),
    response_model=ExchangeRatesResponse,
    dependencies=[Depends(rate_limit("fx_rates", client_ip_key, 60))],
    responses={429: {"model": ProblemDetails}},
)
async def get_exchange_rates(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[ExchangeRateProvider, Depends(get_exchange_rate_provider)],
    cache: Annotated[ExchangeRateCache, Depends(get_exchange_rate_cache)],
) -> ExchangeRatesResponse:
    handler = GetExchangeRatesHandler(
        provider=provider,
        cache=cache,
        fallback_pen_per_usd=Decimal(str(settings.fx_fallback_pen_per_usd)),
    )
    rates = await handler.handle()
    response.headers["Cache-Control"] = "public, max-age=3600"
    return to_exchange_rates_response(rates)


@router.get(
    "/quotes/{search_id}",
    summary="Recuperar una sesión activa de cotización y su podio actual",
    description=(
        "Devuelve el podio vigente con los pesos usados por última vez, sin costo. La "
        "sesión dura 30 minutos desde su creación (RN-10).\n\n"
        "- 🔒 Requiere `Authorization: Bearer <access_token>` de un usuario con correo "
        "verificado.\n"
        "- **Error:** `404 SEARCH_NOT_FOUND` si no existe, expiró o es de otro usuario."
    ),
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
