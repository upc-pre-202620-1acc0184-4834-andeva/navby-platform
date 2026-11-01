import logging
import time
from typing import Any

import httpx

from src.modules.quotes.application.acl.ports.flight_offers_provider import (
    FlightOffersProvider,
)
from src.modules.quotes.application.acl.ports.provider_gate import ProviderGate
from src.modules.quotes.domain.model.value_objects.flight_offer import FlightOffer
from src.modules.quotes.domain.model.value_objects.search_criteria import (
    AirportPair,
    Cabin,
    SearchCriteria,
    TripType,
)
from src.modules.quotes.infrastructure.adapters.flight_api_translator import (
    translate_flightapi_payload,
)
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result

logger = logging.getLogger(__name__)

_CABIN_MAP: dict[Cabin, str] = {
    Cabin.ECONOMY: "Economy",
    Cabin.PREMIUM_ECONOMY: "Premium_Economy",
    Cabin.BUSINESS: "Business",
    Cabin.FIRST: "First",
}


class FlightApiOffersProvider(FlightOffersProvider):
    BASE_URL = "https://api.flightapi.io"

    def __init__(
        self,
        api_key: str,
        gate: ProviderGate,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._api_key = api_key
        self._gate = gate
        self._timeout = timeout_seconds

    def _build_url(self, pair: AirportPair, criteria: SearchCriteria) -> str:
        pax = criteria.passengers
        cabin_str = _CABIN_MAP[criteria.cabin]
        dep = criteria.departure_date.isoformat()
        if criteria.trip_type == TripType.ROUND_TRIP and criteria.return_date is not None:
            ret = criteria.return_date.isoformat()
            return (
                f"{self.BASE_URL}/roundtrip/{self._api_key}/{pair.origin}/{pair.destination}"
                f"/{dep}/{ret}/{pax.adults}/{pax.children}/{pax.infants}"
                f"/{cabin_str}/{criteria.currency.value}"
            )
        return (
            f"{self.BASE_URL}/onewaytrip/{self._api_key}/{pair.origin}/{pair.destination}"
            f"/{dep}/{pax.adults}/{pax.children}/{pax.infants}"
            f"/{cabin_str}/{criteria.currency.value}"
        )

    async def fetch_offers(
        self, pair: AirportPair, criteria: SearchCriteria
    ) -> Result[list[FlightOffer]]:
        url = self._build_url(pair, criteria)
        try:
            async with self._gate.slot():
                return await self._request_with_retry(url, pair, criteria)
        except TimeoutError:
            logger.warning(
                "ProviderGate semaphore wait timed out for pair %s->%s",
                pair.origin,
                pair.destination,
            )
            return Result.failure(
                ApplicationError(
                    code="PROVIDER_UNAVAILABLE",
                    message="Tiempo de espera agotado en la cola de FlightAPI.",
                )
            )

    async def _request_with_retry(
        self, url: str, pair: AirportPair, criteria: SearchCriteria
    ) -> Result[list[FlightOffer]]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for attempt in range(2):
                t0 = time.perf_counter()
                try:
                    resp = await client.get(url)
                except httpx.TimeoutException:
                    logger.warning(
                        "FlightAPI timeout for pair %s->%s",
                        pair.origin,
                        pair.destination,
                    )
                    return Result.failure(
                        ApplicationError(
                            code="PROVIDER_UNAVAILABLE",
                            message="FlightAPI no respondió a tiempo.",
                        )
                    )
                except httpx.RequestError as exc:
                    elapsed = time.perf_counter() - t0
                    if attempt == 0 and elapsed < 5.0:
                        continue
                    logger.error(
                        "FlightAPI connection error for %s->%s: %s",
                        pair.origin,
                        pair.destination,
                        type(exc).__name__,
                    )
                    return Result.failure(
                        ApplicationError(
                            code="PROVIDER_UNAVAILABLE",
                            message="Error de conexión con FlightAPI.",
                        )
                    )

                elapsed = time.perf_counter() - t0
                if 500 <= resp.status_code < 600:
                    if attempt == 0 and elapsed < 5.0:
                        continue
                    logger.error(
                        "FlightAPI HTTP %d for %s->%s",
                        resp.status_code,
                        pair.origin,
                        pair.destination,
                    )
                    return Result.failure(
                        ApplicationError(
                            code="PROVIDER_UNAVAILABLE",
                            message="FlightAPI devolvió un error de servidor.",
                        )
                    )

                if 400 <= resp.status_code < 500:
                    logger.error(
                        "FlightAPI HTTP %d for %s->%s",
                        resp.status_code,
                        pair.origin,
                        pair.destination,
                    )
                    return Result.failure(
                        ApplicationError(
                            code="PROVIDER_UNAVAILABLE",
                            message="FlightAPI rechazó la solicitud.",
                        )
                    )

                try:
                    data: dict[str, Any] = resp.json()
                except Exception:
                    return Result.failure(
                        ApplicationError(
                            code="PROVIDER_UNAVAILABLE",
                            message="Respuesta inválida de FlightAPI.",
                        )
                    )

                offers = translate_flightapi_payload(data, criteria)
                return Result.success(offers)

        return Result.failure(
            ApplicationError(
                code="PROVIDER_UNAVAILABLE",
                message="FlightAPI no disponible.",
            )
        )
