from dataclasses import dataclass

from src.shared.domain.domain_error import DomainError


@dataclass(frozen=True, slots=True)
class ReachabilityResult:
    reachable: bool
    min_stops: int | None

    def __post_init__(self) -> None:
        if self.reachable and self.min_stops not in (0, 1, 2):
            raise DomainError(
                "VALIDATION_ERROR",
                "Reachable route must have min_stops in {0, 1, 2}.",
            )
        if not self.reachable and self.min_stops is not None:
            raise DomainError("VALIDATION_ERROR", "Unreachable route must have min_stops=None.")
