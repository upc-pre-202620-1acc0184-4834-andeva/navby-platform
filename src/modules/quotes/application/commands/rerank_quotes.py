from dataclasses import dataclass
from uuid import UUID

from src.modules.quotes.application.acl.ports.search_session_store import (
    SearchSessionStore,
)
from src.modules.quotes.domain.model.aggregates.quote_search import QuoteSearch
from src.modules.quotes.domain.model.value_objects.preference_weights import (
    PreferenceProfile,
    PreferenceWeights,
)
from src.modules.quotes.domain.model.value_objects.search_id import SearchId
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.domain.domain_error import DomainError


@dataclass(frozen=True, slots=True)
class RerankQuotesCommand:
    user_id: UUID
    search_id: str
    profile: str
    price_weight: float | None = None
    duration_weight: float | None = None
    stops_weight: float | None = None


class RerankQuotesHandler:
    def __init__(self, session_store: SearchSessionStore) -> None:
        self._session_store = session_store

    async def handle(self, cmd: RerankQuotesCommand) -> Result[QuoteSearch]:
        try:
            prof = PreferenceProfile(cmd.profile)
            weights = PreferenceWeights.from_profile(
                prof,
                price=cmd.price_weight,
                duration=cmd.duration_weight,
                stops=cmd.stops_weight,
            )
        except ValueError:
            return Result.failure(
                ApplicationError(
                    code="INVALID_WEIGHTS",
                    message="Perfil de preferencias inválido.",
                )
            )
        except DomainError as exc:
            return Result.failure(ApplicationError(code=exc.code, message=exc.message))

        try:
            sid = SearchId(cmd.search_id)
        except DomainError:
            return Result.failure(
                ApplicationError(
                    code="SEARCH_NOT_FOUND",
                    message="La búsqueda no existe o venció.",
                )
            )

        search = await self._session_store.get(sid)
        if search is None or search.user_id != cmd.user_id:
            return Result.failure(
                ApplicationError(
                    code="SEARCH_NOT_FOUND",
                    message="La búsqueda no existe o venció.",
                )
            )

        search.rank(weights)
        await self._session_store.update(search)
        return Result.success(search)
