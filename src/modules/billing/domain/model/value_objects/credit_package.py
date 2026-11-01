from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CreditPackage:
    code: str
    name: str
    credits: int
    price_pen: Decimal
    usd_reference: Decimal

    @property
    def searches(self) -> int:
        return self.credits // 5


CREDIT_PACKAGES: tuple[CreditPackage, ...] = (
    CreditPackage(
        code="pack_50",
        name="Escapada",
        credits=50,
        price_pen=Decimal("9.90"),
        usd_reference=Decimal("2.49"),
    ),
    CreditPackage(
        code="pack_100",
        name="Viajero Frecuente",
        credits=100,
        price_pen=Decimal("16.90"),
        usd_reference=Decimal("4.49"),
    ),
    CreditPackage(
        code="pack_250",
        name="Nómada",
        credits=250,
        price_pen=Decimal("34.90"),
        usd_reference=Decimal("8.99"),
    ),
)

_BY_CODE: dict[str, CreditPackage] = {p.code: p for p in CREDIT_PACKAGES}


def get_package_by_code(code: str) -> CreditPackage | None:
    return _BY_CODE.get(code.strip())
