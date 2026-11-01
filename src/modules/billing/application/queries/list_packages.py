from src.modules.billing.domain.model.value_objects.credit_package import (
    CREDIT_PACKAGES,
    CreditPackage,
)
from src.shared.application.result import Result


class ListPackagesHandler:
    def handle(self) -> Result[tuple[CreditPackage, ...]]:
        return Result.success(CREDIT_PACKAGES)
