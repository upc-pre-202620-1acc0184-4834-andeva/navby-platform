import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress

logger = logging.getLogger(__name__)


class PeriodicTasks:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task[None]] = []
        self._stop_event = asyncio.Event()

    def register(
        self,
        name: str,
        interval_seconds: float,
        job: Callable[[], Awaitable[object]],
    ) -> None:
        task = asyncio.create_task(
            self._runner(name, interval_seconds, job),
            name=f"periodic:{name}",
        )
        self._tasks.append(task)

    async def _runner(
        self,
        name: str,
        interval_seconds: float,
        job: Callable[[], Awaitable[object]],
    ) -> None:
        while not self._stop_event.is_set():
            try:
                await job()
            except Exception:
                logger.exception("Error executing periodic task %s", name)
            with suppress(TimeoutError):
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval_seconds)

    async def stop_all(self) -> None:
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
