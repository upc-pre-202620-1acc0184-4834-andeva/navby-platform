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

_SKYSCANNER_BASE_URL = "https://www.skyscanner.com"


def _index_by_id(raw: Any) -> dict[str, dict[str, Any]]:
    """Indexa colecciones de FlightAPI tanto si llegan como lista como si llegan como mapa."""
    indexed: dict[str, dict[str, Any]] = {}
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id", item.get("entity_id", item.get("entityId")))
            if item_id is not None:
                indexed[str(item_id)] = item
    elif isinstance(raw, dict):
        for key, item in raw.items():
            if not isinstance(item, dict):
                continue
            indexed[str(key)] = item
            item_id = item.get("id", item.get("entity_id", item.get("entityId")))
            if item_id is not None:
                indexed[str(item_id)] = item
    return indexed


def _normalize_deep_link(raw_link: str) -> str:
    link = raw_link.strip()
    if not link:
        return ""
    if link.startswith("//"):
        return f"https:{link}"
    if link.startswith("/"):
        return f"{_SKYSCANNER_BASE_URL}{link}"
    return link


def _extract_pricing_option(opt: dict[str, Any], itn: dict[str, Any]) -> tuple[Decimal, str] | None:
    items = opt.get("items") or []
    raw_amount = (opt.get("price") or {}).get("amount")
    if raw_amount is None and items and isinstance(items[0], dict):
        raw_amount = (items[0].get("price") or {}).get("amount")

    raw_link = ""
    for item in items:
        if isinstance(item, dict):
            candidate = str(item.get("url") or item.get("deep_link") or "").strip()
            if candidate:
                raw_link = candidate
                break
    if not raw_link:
        raw_link = str(
            opt.get("url")
            or opt.get("deep_link")
            or itn.get("deepLink")
            or itn.get("deep_link")
            or ""
        ).strip()

    deep_link = _normalize_deep_link(raw_link)
    if raw_amount is None or not deep_link:
        return None
    try:
        dec_amount = Decimal(str(raw_amount))
    except Exception:
        return None
    if dec_amount <= Decimal("0"):
        return None
    return (dec_amount, deep_link)


def _resolve_place_iata(
    raw_seg: dict[str, Any],
    code_key: str,
    id_key: str,
    places_by_id: dict[str, dict[str, Any]],
) -> str:
    direct = str(raw_seg.get(code_key) or "").strip().upper()
    if direct:
        return direct
    place_id = raw_seg.get(id_key)
    if place_id is None:
        return ""
    place = places_by_id.get(str(place_id))
    if not place:
        return ""
    code = (
        place.get("display_code")
        or place.get("alt_id")
        or place.get("iata")
        or place.get("code")
        or ""
    )
    return str(code).strip().upper()


def _resolve_carrier(
    raw_seg: dict[str, Any], carriers_by_id: dict[str, dict[str, Any]]
) -> AirlineInfo:
    carrier_id = raw_seg.get("marketing_carrier_id")
    if carrier_id is None:
        carrier_id = raw_seg.get("operating_carrier_id")
    raw_carrier = carriers_by_id.get(str(carrier_id), {}) if carrier_id is not None else {}

    raw_iata = (
        raw_carrier.get("iata")
        or raw_carrier.get("display_code")
        or raw_carrier.get("alt_id")
        or raw_carrier.get("code")
        or "XX"
    )
    airline_iata = str(raw_iata).strip().upper() or "XX"
    airline_name = str(raw_carrier.get("name") or airline_iata).strip() or airline_iata
    airline_logo = str(
        raw_carrier.get("logo") or raw_carrier.get("image_url") or raw_carrier.get("imageUrl") or ""
    ).strip()
    return AirlineInfo(iata=airline_iata, name=airline_name, logo=airline_logo)


def _format_flight_number(raw_number: Any, airline_iata: str) -> str:
    num = str(raw_number or "").strip()
    if num.isdigit() and airline_iata != "XX":
        return f"{airline_iata}{num}"
    return num


def translate_flightapi_payload(
    payload: dict[str, Any], criteria: SearchCriteria
) -> list[FlightOffer]:
    legs_by_id = _index_by_id(payload.get("legs"))
    segments_by_id = _index_by_id(payload.get("segments"))
    places_by_id = _index_by_id(payload.get("places"))
    carriers_by_id = _index_by_id(payload.get("carriers"))

    offers: list[FlightOffer] = []
    for itn in payload.get("itineraries", []):
        if not isinstance(itn, dict):
            continue
        pricing_opts = itn.get("pricing_options") or []
        valid_opts: list[tuple[Decimal, str]] = []
        for opt in pricing_opts:
            if not isinstance(opt, dict):
                continue
            parsed_opt = _extract_pricing_option(opt, itn)
            if parsed_opt is not None:
                valid_opts.append(parsed_opt)

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
            seg_ids = raw_leg.get("segment_ids") or []
            if not seg_ids:
                valid_legs = False
                break

            raw_stops = raw_leg.get("stop_count")
            stop_count = int(raw_stops) if raw_stops is not None else max(0, len(seg_ids) - 1)
            if stop_count > 2:
                valid_legs = False
                break

            domain_segments: list[Segment] = []
            seg_duration_sum = 0
            for seg_id in seg_ids:
                raw_seg = segments_by_id.get(str(seg_id))
                if raw_seg is None:
                    valid_legs = False
                    break

                carrier_info = _resolve_carrier(raw_seg, carriers_by_id)
                if carrier_info.iata not in carrier_map:
                    carrier_map[carrier_info.iata] = carrier_info

                flight_number = _format_flight_number(
                    raw_seg.get("marketing_flight_number"), carrier_info.iata
                )
                dep_str = str(raw_seg.get("departure") or "")
                arr_str = str(raw_seg.get("arrival") or "")
                from_code = _resolve_place_iata(
                    raw_seg, "origin_station_code", "origin_place_id", places_by_id
                )
                to_code = _resolve_place_iata(
                    raw_seg, "destination_station_code", "destination_place_id", places_by_id
                )
                seg_duration_sum += int(raw_seg.get("duration") or 0)

                sig_parts.append(f"{from_code}-{to_code}:{flight_number}@{dep_str}")
                domain_segments.append(
                    Segment(
                        from_iata=from_code,
                        to_iata=to_code,
                        departure=dep_str,
                        arrival=arr_str,
                        flight_number=flight_number,
                        airline_iata=carrier_info.iata,
                    )
                )

            if not valid_legs:
                break

            raw_duration = raw_leg.get("duration")
            if raw_duration is None:
                raw_duration = raw_leg.get("duration_in_minutes")
            leg_duration = int(raw_duration) if raw_duration is not None else 0
            if leg_duration <= 0:
                leg_duration = seg_duration_sum

            direction = LegDirection.OUTBOUND if leg_idx == 0 else LegDirection.INBOUND
            domain_legs.append(
                Leg(
                    direction=direction,
                    departure=str(raw_leg.get("departure") or ""),
                    arrival=str(raw_leg.get("arrival") or ""),
                    duration_minutes=leg_duration,
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
