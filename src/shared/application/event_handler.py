from typing import Protocol

from src.shared.domain.integration_event import IntegrationEvent


class EventHandler(Protocol):
    async def handle(self, event: IntegrationEvent) -> None: ...
