from collections import defaultdict

from src.shared.application.event_handler import EventHandler
from src.shared.domain.integration_event import IntegrationEvent


class InMemoryEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._subscribers[event_type].append(handler)

    async def publish(self, event: IntegrationEvent) -> None:
        for handler in self._subscribers.get(event.event_type, []):
            await handler.handle(event)
