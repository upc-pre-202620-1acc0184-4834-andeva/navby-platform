from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class TransactionType(StrEnum):
    SEARCH_DEBIT = "SEARCH_DEBIT"
    SEARCH_REFUND = "SEARCH_REFUND"
    PURCHASE = "PURCHASE"
    PURCHASE_REVERSAL = "PURCHASE_REVERSAL"
    ACCOUNT_DELETION = "ACCOUNT_DELETION"


@dataclass(frozen=True, slots=True)
class CreditTransaction:
    type: TransactionType
    free_delta: int
    paid_delta: int
    reference_id: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
