from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from src.shared.domain.domain_error import DomainError


class LegDirection(StrEnum):
    OUTBOUND = "OUTBOUND"
    INBOUND = "INBOUND"


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if self.amount < Decimal("0"):
            raise DomainError("VALIDATION_ERROR", "El monto no puede ser negativo.")
        if self.currency not in {"USD", "PEN"}:
            raise DomainError("VALIDATION_ERROR", "Moneda no soportada.")
        quantized = self.amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        object.__setattr__(self, "amount", quantized)

    def formatted(self) -> str:
        return f"{self.amount:.2f}"


@dataclass(frozen=True, slots=True)
class Segment:
    from_iata: str
    to_iata: str
    departure: str
    arrival: str
    flight_number: str
    airline_iata: str


@dataclass(frozen=True, slots=True)
class Leg:
    direction: LegDirection
    departure: str
    arrival: str
    duration_minutes: int
    stops: int
    segments: tuple[Segment, ...]


@dataclass(frozen=True, slots=True)
class AirlineInfo:
    iata: str
    name: str
    logo: str


@dataclass(frozen=True, slots=True)
class FlightOffer:
    offer_id: str
    price: Money
    duration_minutes: int
    stops: int
    legs: tuple[Leg, ...]
    airlines: tuple[AirlineInfo, ...]
    deep_link: str

    def __post_init__(self) -> None:
        if self.price.amount <= Decimal("0"):
            raise DomainError("VALIDATION_ERROR", "El precio de la oferta debe ser > 0.")
        if self.duration_minutes <= 0:
            raise DomainError("VALIDATION_ERROR", "La duración de la oferta debe ser > 0.")
        if any(leg.stops > 2 for leg in self.legs):
            raise DomainError(
                "VALIDATION_ERROR",
                "Ningún tramo puede superar las 2 escalas (RN-05).",
            )

    def first_departure(self) -> str:
        if not self.legs:
            return ""
        return self.legs[0].departure

    def airport_sequence(self) -> tuple[str, ...]:
        seq: list[str] = []
        for leg in self.legs:
            for idx, seg in enumerate(leg.segments):
                if idx == 0:
                    seq.append(seg.from_iata)
                seq.append(seg.to_iata)
        return tuple(seq)

    def airline_sequence(self) -> tuple[str, ...]:
        carriers: list[str] = []
        for leg in self.legs:
            for seg in leg.segments:
                if not carriers or carriers[-1] != seg.airline_iata:
                    carriers.append(seg.airline_iata)
        return tuple(carriers)

    def diversity_key(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return (self.airport_sequence(), self.airline_sequence())


@dataclass(frozen=True, slots=True)
class RankedOffer:
    rank: int
    offer: FlightOffer
    score: float
    match_pct: int
