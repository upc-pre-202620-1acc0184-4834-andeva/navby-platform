from dataclasses import dataclass
from uuid import UUID

from src.modules.quotes.application.acl.ports.search_session_store import (
    SearchSessionStore,
)
from src.modules.quotes.domain.model.aggregates.quote_search import QuoteSearch
from src.modules.quotes.domain.model.value_objects.search_id import SearchId
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.domain.domain_error import DomainError


@dataclass(frozen=True, slots=True)
class GetQuoteSearchQuery:
    user_id: UUID
    search_id: str


class GetQuoteSearchHandler:
    def __init__(self, session_store: SearchSessionStore) -> None:
        self._session_store = session_store

    async def handle(self, query: GetQuoteSearchQuery) -> Result[QuoteSearch]:
        try:
            sid = SearchId(query.search_id)
        except DomainError:
            return Result.failure(
                ApplicationError(
                    code="SEARCH_NOT_FOUND",
                    message="La búsqueda no existe o venció.",
                )
            )

        search = await self._session_store.get(sid)
        if search is None or search.user_id != query.user_id:
            return Result.failure(
                ApplicationError(
                    code="SEARCH_NOT_FOUND",
                    message="La búsqueda no existe o venció.",
                )
            )
        search.credits_charged = 0
        return Result.success(search)
