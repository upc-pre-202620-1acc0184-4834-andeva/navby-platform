from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

# Monedas en las que la webapp puede mostrar precios. Las cotizaciones siempre se piden en USD.
DISPLAY_CURRENCIES = ("USD", "PEN")


@dataclass(frozen=True, slots=True)
class ExchangeRates:
    """Unidades de cada moneda por 1 USD; solo para mostrar precios, nunca para cotizar."""

    rates: dict[str, Decimal]
    as_of: datetime
    source: str  # "provider" o "fallback"
