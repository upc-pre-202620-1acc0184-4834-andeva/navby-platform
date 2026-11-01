from dataclasses import dataclass
from uuid import UUID

from src.modules.billing.domain.model.value_objects.credit_transaction import (
    CreditTransaction,
)
from src.modules.billing.domain.repositories.credit_transaction_repository import (
    CreditTransactionRepository,
)
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.application.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class ListTransactionsQuery:
    user_id: UUID
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True, slots=True)
class PaginatedTransactionsDTO:
    items: list[CreditTransaction]
    page: int
    page_size: int
    total: int


class ListTransactionsHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        tx_repo: CreditTransactionRepository,
    ) -> None:
        self._uow = uow
        self._tx_repo = tx_repo

    async def handle(self, query: ListTransactionsQuery) -> Result[PaginatedTransactionsDTO]:
        if query.page < 1 or not (1 <= query.page_size <= 50):
            return Result.failure(
                ApplicationError(
                    code="VALIDATION_ERROR",
                    message="page debe ser >= 1 y page_size debe estar entre 1 y 50.",
                )
            )

        async with self._uow:
            items, total = await self._tx_repo.list_for_user(
                user_id=query.user_id,
                page=query.page,
                page_size=query.page_size,
            )

        return Result.success(
            PaginatedTransactionsDTO(
                items=items,
                page=query.page,
                page_size=query.page_size,
                total=total,
            )
        )
