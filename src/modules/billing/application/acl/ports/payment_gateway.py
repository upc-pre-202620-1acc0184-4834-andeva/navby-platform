from typing import Protocol

from src.modules.billing.domain.model.aggregates.credit_order import CreditOrder
from src.modules.billing.domain.model.value_objects.payment_info import PaymentInfo


class PaymentGateway(Protocol):
    async def create_preference(self, order: CreditOrder) -> tuple[str, str]: ...

    async def get_payment(self, payment_id: str) -> PaymentInfo | None: ...

    def verify_signature(self, x_signature: str, x_request_id: str, data_id: str) -> bool: ...
