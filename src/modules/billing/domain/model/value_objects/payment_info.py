from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PaymentInfo:
    payment_id: str
    status: str
    external_reference: str
    amount: Decimal
    currency: str
