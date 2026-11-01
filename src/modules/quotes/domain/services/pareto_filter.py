from decimal import Decimal

from src.modules.quotes.domain.model.value_objects.flight_offer import FlightOffer


class ParetoFilter:
    """Filtra ofertas dominadas en (precio, duración, escalas) en O(N^2)."""

    def filter(self, offers: list[FlightOffer]) -> list[FlightOffer]:
        if not offers:
            return []

        # Deduplicate offers with identical (price, duration, stops) keeping min offer_id
        best_by_criteria: dict[tuple[Decimal, int, int], FlightOffer] = {}
        for offer in offers:
            key = (offer.price.amount, offer.duration_minutes, offer.stops)
            existing = best_by_criteria.get(key)
            if existing is None or offer.offer_id < existing.offer_id:
                best_by_criteria[key] = offer

        unique_offers = list(best_by_criteria.values())
        front: list[FlightOffer] = []
        for a in unique_offers:
            dominated = False
            for b in unique_offers:
                if a.offer_id == b.offer_id:
                    continue
                if (
                    b.price.amount <= a.price.amount
                    and b.duration_minutes <= a.duration_minutes
                    and b.stops <= a.stops
                    and (
                        b.price.amount < a.price.amount
                        or b.duration_minutes < a.duration_minutes
                        or b.stops < a.stops
                    )
                ):
                    dominated = True
                    break
            if not dominated:
                front.append(a)

        front.sort(
            key=lambda o: (
                o.price.amount,
                o.duration_minutes,
                o.stops,
                o.first_departure(),
                o.offer_id,
            )
        )
        return front
