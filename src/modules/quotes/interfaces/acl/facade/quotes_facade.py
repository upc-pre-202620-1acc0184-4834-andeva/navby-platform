from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from src.modules.quotes.application.acl.ports.search_session_store import (
    SearchSessionStore,
)
from src.modules.quotes.domain.model.value_objects.search_id import SearchId
from src.modules.routing.interfaces.acl.facade.routing_facade import RoutingFacade
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.domain.domain_error import DomainError


@dataclass(frozen=True, slots=True)
class OfferSnapshotDTO:
    offer_id: str
    trip_type: str
    origin: str
    destination: str
    departure_date: date
    return_date: date | None
    quoted_at: datetime
    snapshot: dict[str, Any]


class QuotesFacade:
    def __init__(
        self,
        session_store: SearchSessionStore,
        routing_facade: RoutingFacade,
    ) -> None:
        self._session_store = session_store
        self._routing = routing_facade

    async def get_offer(
        self,
        user_id: UUID,
        search_id: str,
        offer_id: str,
    ) -> Result[OfferSnapshotDTO]:
        try:
            sid = SearchId(search_id)
        except DomainError:
            return Result.failure(
                ApplicationError(
                    code="SEARCH_NOT_FOUND",
                    message="La búsqueda no existe o venció.",
                )
            )

        search = await self._session_store.get(sid)
        if search is None or search.user_id != user_id:
            return Result.failure(
                ApplicationError(
                    code="SEARCH_NOT_FOUND",
                    message="La búsqueda no existe o venció.",
                )
            )

        ranked_offer = search.find_ranked_offer(offer_id)
        if ranked_offer is None:
            return Result.failure(
                ApplicationError(
                    code="OFFER_NOT_FOUND",
                    message="La oferta no existe en la frontera de esta búsqueda.",
                )
            )

        from src.modules.quotes.interfaces.rest.assemblers import (
            to_podium_offer_response,
        )

        podium_item = to_podium_offer_response(
            ranked_offer=ranked_offer,
            t_min_minutes=search.t_min_minutes,
            routing_facade=self._routing,
        )
        snapshot = podium_item.model_dump()
        snapshot["profile"] = search.weights.profile.value
        snapshot["weights"] = {
            "price": search.weights.price,
            "duration": search.weights.duration,
            "stops": search.weights.stops,
        }
        snapshot["quoted_at"] = search.created_at.strftime("%Y-%m-%dT%H:%M:%SZ")

        first_leg = ranked_offer.offer.legs[0]
        origin = first_leg.segments[0].from_iata
        destination = first_leg.segments[-1].to_iata

        return Result.success(
            OfferSnapshotDTO(
                offer_id=ranked_offer.offer.offer_id,
                trip_type=search.criteria.trip_type.value,
                origin=origin,
                destination=destination,
                departure_date=search.criteria.departure_date,
                return_date=search.criteria.return_date,
                quoted_at=search.created_at,
                snapshot=snapshot,
            )
        )
