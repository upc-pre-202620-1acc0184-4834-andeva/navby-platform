from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID

from src.shared.domain.integration_event import IntegrationEvent


@dataclass(frozen=True, slots=True)
class UserDeleted(IntegrationEvent):
    event_type: ClassVar[str] = "iam.user_deleted"
    user_id: UUID

    def to_payload(self) -> dict[str, Any]:
        return {"user_id": str(self.user_id)}

    @staticmethod
    def from_payload(
        event_id: UUID,
        occurred_at: datetime,
        payload: dict[str, Any],
    ) -> "UserDeleted":
        return UserDeleted(
            event_id=event_id,
            occurred_at=occurred_at,
            user_id=UUID(str(payload["user_id"])),
        )
