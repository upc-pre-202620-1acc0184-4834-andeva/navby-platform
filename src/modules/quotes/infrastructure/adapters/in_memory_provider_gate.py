import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from src.modules.quotes.application.acl.ports.provider_gate import ProviderGate


class InMemoryProviderGate(ProviderGate):
    def __init__(
        self,
        max_concurrency: int = 5,
        wait_timeout_seconds: float = 10.0,
    ) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._wait_timeout = wait_timeout_seconds

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        await asyncio.wait_for(self._semaphore.acquire(), timeout=self._wait_timeout)
        try:
            yield
        finally:
            self._semaphore.release()
