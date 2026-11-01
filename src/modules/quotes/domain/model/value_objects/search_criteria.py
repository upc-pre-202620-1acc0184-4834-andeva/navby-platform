from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from src.shared.domain.domain_error import DomainError


class TripType(StrEnum):
    ONE_WAY = "ONE_WAY"
    ROUND_TRIP = "ROUND_TRIP"


class Cabin(StrEnum):
    ECONOMY = "ECONOMY"
    PREMIUM_ECONOMY = "PREMIUM_ECONOMY"
    BUSINESS = "BUSINESS"
    FIRST = "FIRST"


class Currency(StrEnum):
    USD = "USD"
    PEN = "PEN"


@dataclass(frozen=True, slots=True)
class PassengerMix:
    adults: int
    children: int = 0
    infants: int = 0

    def __post_init__(self) -> None:
        if not (1 <= self.adults <= 9):
            raise DomainError(
                "VALIDATION_ERROR",
                "Debe haber entre 1 y 9 adultos.",
            )
        if not (0 <= self.children <= 8):
            raise DomainError(
                "VALIDATION_ERROR",
                "Los niños deben estar entre 0 y 8.",
            )
        if self.infants < 0 or self.infants > self.adults:
            raise DomainError(
                "VALIDATION_ERROR",
                "Los infantes no pueden superar al número de adultos.",
            )
        if self.adults + self.children + self.infants > 9:
            raise DomainError(
                "VALIDATION_ERROR",
                "El total de pasajeros no puede superar 9.",
            )


@dataclass(frozen=True, slots=True)
class AirportPair:
    origin: str
    destination: str

    def __post_init__(self) -> None:
        orig = self.origin.strip().upper()
        dest = self.destination.strip().upper()
        if len(orig) != 3 or len(dest) != 3 or orig == dest:
            raise DomainError(
                "VALIDATION_ERROR",
                "El par de aeropuertos debe tener códigos IATA distintos de 3 letras.",
            )
        object.__setattr__(self, "origin", orig)
        object.__setattr__(self, "destination", dest)

    def cache_key(self, criteria: "SearchCriteria") -> str:
        ret_part = criteria.return_date.isoformat() if criteria.return_date is not None else "-"
        pax = criteria.passengers
        return (
            f"{criteria.trip_type.value}:{self.origin}:{self.destination}:"
            f"{criteria.departure_date.isoformat()}:{ret_part}:"
            f"{criteria.cabin.value}:{pax.adults}-{pax.children}-{pax.infants}:"
            f"{criteria.currency.value}"
        )


@dataclass(frozen=True, slots=True)
class SearchCriteria:
    trip_type: TripType
    origins: tuple[str, ...]
    destinations: tuple[str, ...]
    departure_date: date
    return_date: date | None
    passengers: PassengerMix
    cabin: Cabin
    currency: Currency
    today_lima: date | None = None

    def __post_init__(self) -> None:
        orig_clean = tuple(dict.fromkeys(c.strip().upper() for c in self.origins if c.strip()))
        dest_clean = tuple(dict.fromkeys(c.strip().upper() for c in self.destinations if c.strip()))
        if not (1 <= len(orig_clean) <= 5) or not (1 <= len(dest_clean) <= 5):
            raise DomainError(
                "VALIDATION_ERROR",
                "Cada lado debe tener entre 1 y 5 aeropuertos.",
            )
        if any(len(c) != 3 or not c.isalpha() for c in (*orig_clean, *dest_clean)):
            raise DomainError(
                "VALIDATION_ERROR",
                "Todos los códigos IATA deben tener 3 letras.",
            )
        if set(orig_clean) & set(dest_clean):
            raise DomainError(
                "VALIDATION_ERROR",
                "Origen y destino no pueden compartir aeropuertos.",
            )
        object.__setattr__(self, "origins", orig_clean)
        object.__setattr__(self, "destinations", dest_clean)

        if self.trip_type == TripType.ROUND_TRIP and self.return_date is None:
            raise DomainError(
                "VALIDATION_ERROR",
                "Un viaje de ida y vuelta requiere return_date.",
            )
        if self.trip_type == TripType.ONE_WAY and self.return_date is not None:
            raise DomainError(
                "VALIDATION_ERROR",
                "Un viaje de solo ida no admite return_date.",
            )
        if self.return_date is not None and self.return_date < self.departure_date:
            raise DomainError(
                "VALIDATION_ERROR",
                "La fecha de retorno no puede ser anterior a la de salida.",
            )
        if self.today_lima is not None:
            if self.departure_date < self.today_lima:
                raise DomainError(
                    "VALIDATION_ERROR",
                    "La fecha de salida no puede ser anterior a hoy (hora de Lima).",
                )
            max_days = (
                (self.return_date - self.today_lima).days
                if self.return_date is not None
                else (self.departure_date - self.today_lima).days
            )
            if max_days > 330:
                raise DomainError(
                    "VALIDATION_ERROR",
                    "Las fechas no pueden superar 330 días a futuro.",
                )

    def pairs(self) -> list[AirportPair]:
        return [
            AirportPair(origin=o, destination=d) for o in self.origins for d in self.destinations
        ]
