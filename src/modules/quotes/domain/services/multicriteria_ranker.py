import math

from src.modules.quotes.domain.model.value_objects.flight_offer import (
    FlightOffer,
    RankedOffer,
)
from src.modules.quotes.domain.model.value_objects.preference_weights import (
    PreferenceWeights,
)


class MulticriteriaRanker:
    """Calcula el puntaje ponderado S y elige el podio diverso de hasta 3 ofertas."""

    def score_all(
        self, front: list[FlightOffer], weights: PreferenceWeights
    ) -> list[tuple[float, FlightOffer]]:
        if not front:
            return []

        prices = [float(o.price.amount) for o in front]
        durations = [float(o.duration_minutes) for o in front]
        stops_list = [float(o.stops) for o in front]

        p_min, p_max = min(prices), max(prices)
        t_min, t_max = min(durations), max(durations)
        e_min, e_max = min(stops_list), max(stops_list)

        p_span = p_max - p_min
        t_span = t_max - t_min
        e_span = e_max - e_min

        scored: list[tuple[float, FlightOffer]] = []
        for offer in front:
            p_norm = (float(offer.price.amount) - p_min) / p_span if p_span > 0.0 else 0.0
            t_norm = (float(offer.duration_minutes) - t_min) / t_span if t_span > 0.0 else 0.0
            e_norm = (float(offer.stops) - e_min) / e_span if e_span > 0.0 else 0.0

            s_val = math.sqrt(
                weights.price * (p_norm * p_norm)
                + weights.duration * (t_norm * t_norm)
                + weights.stops * (e_norm * e_norm)
            )
            scored.append((s_val, offer))

        scored.sort(
            key=lambda item: (
                round(item[0], 12),
                item[1].price.amount,
                item[1].duration_minutes,
                item[1].first_departure(),
                item[1].offer_id,
            )
        )
        return scored

    def rank(self, front: list[FlightOffer], weights: PreferenceWeights) -> list[RankedOffer]:
        scored = self.score_all(front, weights)
        podium: list[RankedOffer] = []
        seen_diversity: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
        for s_val, offer in scored:
            div_key = offer.diversity_key()
            if div_key in seen_diversity:
                continue
            seen_diversity.add(div_key)
            rank_num = len(podium) + 1
            match_pct = max(0, min(100, round((1.0 - s_val) * 100)))
            podium.append(
                RankedOffer(
                    rank=rank_num,
                    offer=offer,
                    score=s_val,
                    match_pct=match_pct,
                )
            )
            if len(podium) == 3:
                break

        return podium
