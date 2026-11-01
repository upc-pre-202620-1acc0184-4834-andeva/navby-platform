from src.modules.quotes.domain.model.aggregates.quote_search import QuoteSearch
from src.modules.quotes.domain.model.value_objects.flight_offer import RankedOffer
from src.modules.quotes.interfaces.rest.schemas import (
    AirlineResponse,
    AirportGeoResponse,
    LegResponse,
    MoneyResponse,
    PairQuotedResponse,
    PodiumOfferResponse,
    PodiumResponse,
    PreferencesResponse,
    SegmentResponse,
    WeightsInput,
)
from src.modules.routing.interfaces.acl.facade.routing_facade import RoutingFacade

PRICE_DISCLAIMER = "Precio referencial obtenido de terceros; se confirma en el sitio del vendedor."


def to_podium_offer_response(
    ranked_offer: RankedOffer,
    t_min_minutes: int,
    routing_facade: RoutingFacade,
) -> PodiumOfferResponse:
    offer = ranked_offer.offer
    iatas: list[str] = []
    legs_resp: list[LegResponse] = []
    for leg in offer.legs:
        segs_resp: list[SegmentResponse] = []
        for seg in leg.segments:
            if seg.from_iata not in iatas:
                iatas.append(seg.from_iata)
            if seg.to_iata not in iatas:
                iatas.append(seg.to_iata)
            segs_resp.append(
                SegmentResponse(
                    from_iata=seg.from_iata,
                    to_iata=seg.to_iata,
                    departure=seg.departure,
                    arrival=seg.arrival,
                    flight_number=seg.flight_number,
                    airline=seg.airline_iata,
                )
            )
        legs_resp.append(
            LegResponse(
                direction=leg.direction.value,
                departure=leg.departure,
                arrival=leg.arrival,
                duration_minutes=leg.duration_minutes,
                stops=leg.stops,
                segments=segs_resp,
            )
        )

    airport_dtos = routing_facade.get_airports(iatas)
    airports_resp = [
        AirportGeoResponse(
            iata=ap.iata,
            lat=ap.lat,
            lon=ap.lon,
            timezone=ap.timezone,
        )
        for ap in airport_dtos
    ]
    extra_minutes = max(0, offer.duration_minutes - t_min_minutes)
    return PodiumOfferResponse(
        rank=ranked_offer.rank,
        offer_id=offer.offer_id,
        score=round(ranked_offer.score, 4),
        match_pct=ranked_offer.match_pct,
        price=MoneyResponse(
            amount=offer.price.formatted(),
            currency=offer.price.currency,
        ),
        duration_minutes=offer.duration_minutes,
        extra_minutes_vs_t_min=extra_minutes,
        stops=offer.stops,
        airlines=[AirlineResponse(iata=a.iata, name=a.name, logo=a.logo) for a in offer.airlines],
        legs=legs_resp,
        airports=airports_resp,
        deep_link=offer.deep_link,
    )


def to_podium_response(search: QuoteSearch, routing_facade: RoutingFacade) -> PodiumResponse:
    return PodiumResponse(
        search_id=search.id.value,
        expires_at=search.expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        credits_charged=search.credits_charged,
        credits_remaining=search.credits_remaining,
        partial=search.partial,
        pairs_quoted=[
            PairQuotedResponse(origin=p.origin, destination=p.destination)
            for p in search.pairs_quoted
        ],
        t_min_minutes=search.t_min_minutes,
        offers_received=search.offers_received,
        pareto_size=len(search.pareto_front),
        preferences=PreferencesResponse(
            profile=search.weights.profile.value,
            weights=WeightsInput(
                price=search.weights.price,
                duration=search.weights.duration,
                stops=search.weights.stops,
            ),
        ),
        price_disclaimer=PRICE_DISCLAIMER,
        podium=[
            to_podium_offer_response(ro, search.t_min_minutes, routing_facade)
            for ro in search.podium
        ],
    )
