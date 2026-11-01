import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from src.modules.billing.interfaces.acl.facade.billing_facade import BillingFacade
from src.modules.quotes.application.acl.ports.flight_offers_provider import (
    FlightOffersProvider,
)
from src.modules.quotes.application.acl.ports.offer_cache import OfferCache
from src.modules.quotes.application.acl.ports.search_lock import SearchLock
from src.modules.quotes.application.acl.ports.search_session_store import (
    SearchSessionStore,
)
from src.modules.quotes.domain.model.aggregates.quote_search import QuoteSearch
from src.modules.quotes.domain.model.value_objects.flight_offer import FlightOffer
from src.modules.quotes.domain.model.value_objects.preference_weights import (
    PreferenceProfile,
    PreferenceWeights,
)
from src.modules.quotes.domain.model.value_objects.search_criteria import (
    AirportPair,
    Cabin,
    Currency,
    PassengerMix,
    SearchCriteria,
    TripType,
)
from src.modules.quotes.domain.model.value_objects.search_id import SearchId
from src.modules.routing.interfaces.acl.facade.routing_facade import RoutingFacade
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.domain.domain_error import DomainError

LIMA_TZ = ZoneInfo("America/Lima")


@dataclass(frozen=True, slots=True)
class SearchQuotesCommand:
    user_id: UUID
    trip_type: str
    origins: list[str]
    destinations: list[str]
    departure_date: str
    return_date: str | None
    adults: int
    children: int
    infants: int
    cabin: str
    currency: str
    profile: str = "BALANCED"
    price_weight: float | None = None
    duration_weight: float | None = None
    stops_weight: float | None = None


class SearchQuotesHandler:
    def __init__(
        self,
        routing_facade: RoutingFacade,
        billing_facade: BillingFacade,
        offer_cache: OfferCache,
        session_store: SearchSessionStore,
        search_lock: SearchLock,
        offers_provider: FlightOffersProvider,
    ) -> None:
        self._routing = routing_facade
        self._billing = billing_facade
        self._cache = offer_cache
        self._session_store = session_store
        self._lock = search_lock
        self._provider = offers_provider

    async def handle(self, cmd: SearchQuotesCommand) -> Result[QuoteSearch]:
        now = datetime.now(UTC)
        today_lima = now.astimezone(LIMA_TZ).date()

        try:
            trip_enum = TripType(cmd.trip_type)
            cabin_enum = Cabin(cmd.cabin)
            currency_enum = Currency(cmd.currency)
            dep_date = date.fromisoformat(cmd.departure_date)
            ret_date = date.fromisoformat(cmd.return_date) if cmd.return_date is not None else None
            pax = PassengerMix(
                adults=cmd.adults,
                children=cmd.children,
                infants=cmd.infants,
            )
            criteria = SearchCriteria(
                trip_type=trip_enum,
                origins=tuple(cmd.origins),
                destinations=tuple(cmd.destinations),
                departure_date=dep_date,
                return_date=ret_date,
                passengers=pax,
                cabin=cabin_enum,
                currency=currency_enum,
                today_lima=today_lima,
            )
        except ValueError:
            return Result.failure(
                ApplicationError(
                    code="VALIDATION_ERROR",
                    message="Parámetros de búsqueda inválidos.",
                )
            )
        except DomainError as exc:
            return Result.failure(ApplicationError(code=exc.code, message=exc.message))

        try:
            prof = PreferenceProfile(cmd.profile)
            weights = PreferenceWeights.from_profile(
                prof,
                price=cmd.price_weight,
                duration=cmd.duration_weight,
                stops=cmd.stops_weight,
            )
        except ValueError:
            return Result.failure(
                ApplicationError(
                    code="INVALID_WEIGHTS",
                    message="Perfil de preferencias inválido.",
                )
            )
        except DomainError as exc:
            return Result.failure(ApplicationError(code=exc.code, message=exc.message))

        if not await self._session_store.ping():
            return Result.failure(
                ApplicationError(
                    code="PROVIDER_UNAVAILABLE",
                    message="El almacén de sesiones no está disponible.",
                )
            )

        try:
            acquired = await self._lock.acquire(cmd.user_id)
        except Exception:
            return Result.failure(
                ApplicationError(
                    code="PROVIDER_UNAVAILABLE",
                    message="No se pudo adquirir el candado de búsqueda en Redis.",
                )
            )
        if not acquired:
            return Result.failure(
                ApplicationError(
                    code="SEARCH_IN_PROGRESS",
                    message="Ya tienes una cotización en curso.",
                )
            )

        try:
            pairs_res = self._routing.select_pairs(
                origins=list(criteria.origins),
                destinations=list(criteria.destinations),
                round_trip=(criteria.trip_type == TripType.ROUND_TRIP),
            )
            if pairs_res.is_failure:
                return Result.failure(pairs_res.error)
            selected_dtos = pairs_res.value
            if not selected_dtos:
                return Result.failure(
                    ApplicationError(
                        code="ROUTE_NOT_REACHABLE",
                        message=(
                            "No existe ruta alcanzable con hasta 2 escalas "
                            "entre las ciudades indicadas."
                        ),
                    )
                )

            t_min_minutes = min(p.t_min_minutes for p in selected_dtos)
            pairs = tuple(
                AirportPair(origin=p.origin, destination=p.destination) for p in selected_dtos
            )

            cached_offers: list[FlightOffer] = []
            uncached_pairs: list[AirportPair] = []
            for pair in pairs:
                key = pair.cache_key(criteria)
                hit = await self._cache.get(key)
                if hit is not None:
                    cached_offers.extend(hit)
                else:
                    uncached_pairs.append(pair)

            search_id = SearchId.generate()
            credits_charged = 0
            credits_remaining = await self._billing.get_total_credits(cmd.user_id)
            partial = False

            if uncached_pairs:
                debit_res = await self._billing.debit_search(cmd.user_id, search_id.value)
                if debit_res.is_failure:
                    return Result.failure(debit_res.error)
                credits_charged = debit_res.value.credits_charged
                credits_remaining = debit_res.value.credits_remaining

                tasks = [
                    asyncio.wait_for(self._provider.fetch_offers(p, criteria), timeout=30.0)
                    for p in uncached_pairs
                ]
                raw_results = await asyncio.gather(*tasks, return_exceptions=True)

                failed_calls = 0
                fetched_offers: list[FlightOffer] = []
                for pair, res_item in zip(uncached_pairs, raw_results, strict=True):
                    if isinstance(res_item, BaseException) or res_item.is_failure:
                        failed_calls += 1
                    else:
                        pair_offers = res_item.value
                        fetched_offers.extend(pair_offers)
                        if pair_offers:
                            await self._cache.put(pair.cache_key(criteria), pair_offers)

                all_offers = cached_offers + fetched_offers
                all_calls_failed = failed_calls == len(uncached_pairs)

                if all_calls_failed or len(all_offers) == 0:
                    refund_res = await self._billing.refund_search(cmd.user_id, search_id.value)
                    credits_charged = 0
                    credits_remaining = refund_res.value
                    if all_calls_failed and not cached_offers:
                        return Result.failure(
                            ApplicationError(
                                code="PROVIDER_UNAVAILABLE",
                                message=(
                                    "El proveedor de vuelos no está disponible en este momento."
                                ),
                            )
                        )

                if failed_calls > 0:
                    partial = True
            else:
                all_offers = cached_offers

            quote_search = QuoteSearch.create(
                search_id=search_id,
                user_id=cmd.user_id,
                criteria=criteria,
                pairs_quoted=pairs,
                offers=all_offers,
                t_min_minutes=t_min_minutes,
                weights=weights,
                partial=partial,
                credits_charged=credits_charged,
                credits_remaining=credits_remaining,
                now=now,
            )
            await self._session_store.create(quote_search)
            return Result.success(quote_search)
        finally:
            with contextlib.suppress(Exception):
                await self._lock.release(cmd.user_id)
