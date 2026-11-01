from typing import Protocol

from src.modules.quotes.domain.model.aggregates.quote_search import QuoteSearch
from src.modules.quotes.domain.model.value_objects.search_id import SearchId


class SearchSessionStore(Protocol):
    async def ping(self) -> bool: ...

    async def get(self, search_id: SearchId) -> QuoteSearch | None: ...

    async def create(self, search: QuoteSearch) -> None: ...

    async def update(self, search: QuoteSearch) -> None: ...
