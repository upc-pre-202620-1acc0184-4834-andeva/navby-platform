from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

from src.shared.domain.domain_event import DomainEvent


@dataclass(frozen=True, slots=True)
class IntegrationEvent(DomainEvent, ABC):
    event_type: ClassVar[str]

    @abstractmethod
    def to_payload(self) -> dict[str, Any]:
        """Serialize integration event payload for the transactional outbox."""
