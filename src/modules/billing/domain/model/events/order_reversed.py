from dataclasses import dataclass
from uuid import UUID

from src.shared.domain.domain_event import DomainEvent


@dataclass(frozen=True, slots=True)
class OrderReversed(DomainEvent):
    order_id: UUID
    user_id: UUID
    credits: int
    payment_id: str
