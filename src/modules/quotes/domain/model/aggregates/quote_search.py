from datetime import UTC, datetime, timedelta
from uuid import UUID

from src.modules.quotes.domain.model.value_objects.flight_offer import (
    FlightOffer,
    RankedOffer,
)
from src.modules.quotes.domain.model.value_objects.preference_weights import (
    PreferenceWeights,
)
from src.modules.quotes.domain.model.value_objects.search_criteria import (
    AirportPair,
    SearchCriteria,
)
from src.modules.quotes.domain.model.value_objects.search_id import SearchId
from src.modules.quotes.domain.services.multicriteria_ranker import MulticriteriaRanker
from src.modules.quotes.domain.services.pareto_filter import ParetoFilter
from src.shared.domain.aggregate_root import AggregateRoot


class QuoteSearch(AggregateRoot):
    SESSION_TTL_SECONDS = 1800

    def __init__(
        self,
        id: SearchId,
        user_id: UUID,
        criteria: SearchCriteria,
        pairs_quoted: tuple[AirportPair, ...],
        pareto_front: list[FlightOffer],
        offers_received: int,
        t_min_minutes: int,
        weights: PreferenceWeights,
        podium: list[RankedOffer],
        partial: bool,
        credits_charged: int,
        credits_remaining: int,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        super().__init__()
        self.id = id
        self.user_id = user_id
        self.criteria = criteria
        self.pairs_quoted = pairs_quoted
        self.pareto_front = pareto_front
        self.offers_received = offers_received
        self.t_min_minutes = t_min_minutes
        self.weights = weights
        self.podium = podium
        self.partial = partial
        self.credits_charged = credits_charged
        self.credits_remaining = credits_remaining
        self.created_at = created_at
        self.expires_at = expires_at

    @staticmethod
    def create(
        search_id: SearchId,
        user_id: UUID,
        criteria: SearchCriteria,
        pairs_quoted: tuple[AirportPair, ...],
        offers: list[FlightOffer],
        t_min_minutes: int,
        weights: PreferenceWeights,
        partial: bool,
        credits_charged: int,
        credits_remaining: int,
        now: datetime | None = None,
    ) -> "QuoteSearch":
        ts = now or datetime.now(UTC)
        # Deduplicate by offer_id across pairs before ParetoFilter
        by_id: dict[str, FlightOffer] = {}
        for o in offers:
            if o.offer_id not in by_id or o.price.amount < by_id[o.offer_id].price.amount:
                by_id[o.offer_id] = o
        deduped = list(by_id.values())

        pf = ParetoFilter()
        ranker = MulticriteriaRanker()
        pareto = pf.filter(deduped)
        podium = ranker.rank(pareto, weights)

        return QuoteSearch(
            id=search_id,
            user_id=user_id,
            criteria=criteria,
            pairs_quoted=pairs_quoted,
            pareto_front=pareto,
            offers_received=len(offers),
            t_min_minutes=t_min_minutes,
            weights=weights,
            podium=podium,
            partial=partial,
            credits_charged=credits_charged,
            credits_remaining=credits_remaining,
            created_at=ts,
            expires_at=ts + timedelta(seconds=QuoteSearch.SESSION_TTL_SECONDS),
        )

    def rank(self, weights: PreferenceWeights) -> None:
        self.weights = weights
        self.podium = MulticriteriaRanker().rank(self.pareto_front, weights)
        self.credits_charged = 0

    def find_offer(self, offer_id: str) -> FlightOffer | None:
        for offer in self.pareto_front:
            if offer.offer_id == offer_id:
                return offer
        return None

    def find_ranked_offer(self, offer_id: str) -> RankedOffer | None:
        for ro in self.podium:
            if ro.offer.offer_id == offer_id:
                return ro
        offer = self.find_offer(offer_id)
        if offer is None:
            return None
        # Compute score for offer if it is in pareto_front but outside top-3 podium
        for idx, (s_val, candidate) in enumerate(
            MulticriteriaRanker().score_all(self.pareto_front, self.weights), start=1
        ):
            if candidate.offer_id == offer_id:
                return RankedOffer(
                    rank=idx,
                    offer=candidate,
                    score=s_val,
                    match_pct=max(0, min(100, round((1.0 - s_val) * 100))),
                )
        return RankedOffer(rank=0, offer=offer, score=0.0, match_pct=100)
