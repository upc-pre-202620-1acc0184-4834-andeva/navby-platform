import hashlib
from decimal import Decimal
from typing import Any

from src.modules.quotes.domain.model.value_objects.flight_offer import (
    AirlineInfo,
    FlightOffer,
    Leg,
    LegDirection,
    Money,
    Segment,
)
from src.modules.quotes.domain.model.value_objects.search_criteria import SearchCriteria
from src.shared.domain.domain_error import DomainError


def translate_flightapi_payload(
    payload: dict[str, Any], criteria: SearchCriteria
) -> list[FlightOffer]:
    legs_by_id: dict[str, dict[str, Any]] = {
        str(leg["id"]): leg for leg in payload.get("legs", []) if "id" in leg
    }
    segments_by_id: dict[str, dict[str, Any]] = {
        str(seg["id"]): seg for seg in payload.get("segments", []) if "id" in seg
    }
    carriers_by_id: dict[str, dict[str, Any]] = {
        str(c["id"]): c for c in payload.get("carriers", []) if "id" in c
    }

    offers: list[FlightOffer] = []
    for itn in payload.get("itineraries", []):
        pricing_opts = itn.get("pricing_options") or []
        valid_opts: list[tuple[Decimal, str]] = []
        for opt in pricing_opts:
            raw_amount = (opt.get("price") or {}).get("amount")
            items = opt.get("items") or []
            deep_link = str(items[0].get("deep_link") or "").strip() if items else ""
            if raw_amount is None or not deep_link:
                continue
            try:
                dec_amount = Decimal(str(raw_amount))
            except Exception:
                continue
            if dec_amount > Decimal("0"):
                valid_opts.append((dec_amount, deep_link))

        if not valid_opts:
            continue

        valid_opts.sort(key=lambda x: x[0])
        min_amount, best_deep_link = valid_opts[0]

        leg_ids = itn.get("leg_ids") or []
        if not leg_ids:
            continue

        domain_legs: list[Leg] = []
        carrier_map: dict[str, AirlineInfo] = {}
        sig_parts: list[str] = []
        valid_legs = True

        for leg_idx, leg_id in enumerate(leg_ids):
            raw_leg = legs_by_id.get(str(leg_id))
            if raw_leg is None:
                valid_legs = False
                break
            stop_count = int(raw_leg.get("stop_count", 0))
            if stop_count > 2:
                valid_legs = False
                break

            seg_ids = raw_leg.get("segment_ids") or []
            if not seg_ids:
                valid_legs = False
                break

            domain_segments: list[Segment] = []
            for seg_id in seg_ids:
                raw_seg = segments_by_id.get(str(seg_id))
                if raw_seg is None:
                    valid_legs = False
                    break
                carrier_id = str(raw_seg.get("marketing_carrier_id", ""))
                raw_carrier = carriers_by_id.get(carrier_id, {})
                airline_iata = str(raw_carrier.get("iata") or "XX")
                airline_name = str(raw_carrier.get("name") or airline_iata)
                airline_logo = str(raw_carrier.get("logo") or "")
                if airline_iata not in carrier_map:
                    carrier_map[airline_iata] = AirlineInfo(
                        iata=airline_iata,
                        name=airline_name,
                        logo=airline_logo,
                    )

                flight_number = str(raw_seg.get("marketing_flight_number") or "")
                dep_str = str(raw_seg.get("departure") or "")
                arr_str = str(raw_seg.get("arrival") or "")
                from_code = str(raw_seg.get("origin_station_code") or "")
                to_code = str(raw_seg.get("destination_station_code") or "")

                sig_parts.append(f"{from_code}-{to_code}:{flight_number}@{dep_str}")
                domain_segments.append(
                    Segment(
                        from_iata=from_code,
                        to_iata=to_code,
                        departure=dep_str,
                        arrival=arr_str,
                        flight_number=flight_number,
                        airline_iata=airline_iata,
                    )
                )

            if not valid_legs:
                break

            direction = LegDirection.OUTBOUND if leg_idx == 0 else LegDirection.INBOUND
            domain_legs.append(
                Leg(
                    direction=direction,
                    departure=str(raw_leg.get("departure") or ""),
                    arrival=str(raw_leg.get("arrival") or ""),
                    duration_minutes=int(raw_leg.get("duration_in_minutes", 0)),
                    stops=stop_count,
                    segments=tuple(domain_segments),
                )
            )

        if not valid_legs or not domain_legs:
            continue

        sig_raw = "|".join(sig_parts) + f"|{criteria.cabin.value}"
        offer_id = hashlib.sha256(sig_raw.encode("utf-8")).hexdigest()[:16]
        total_duration = sum(leg_item.duration_minutes for leg_item in domain_legs)
        total_stops = sum(leg_item.stops for leg_item in domain_legs)

        try:
            offer = FlightOffer(
                offer_id=offer_id,
                price=Money(amount=min_amount, currency=criteria.currency.value),
                duration_minutes=total_duration,
                stops=total_stops,
                legs=tuple(domain_legs),
                airlines=tuple(carrier_map.values()),
                deep_link=best_deep_link,
            )
            offers.append(offer)
        except DomainError:
            continue

    return offers
