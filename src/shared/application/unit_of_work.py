from types import TracebackType
from typing import Any, Protocol, Self


class UnitOfWork(Protocol):
    @property
    def session(self) -> Any: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
