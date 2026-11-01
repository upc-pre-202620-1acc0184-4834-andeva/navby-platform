from dataclasses import dataclass
from enum import StrEnum

from src.shared.domain.domain_error import DomainError


class PreferenceProfile(StrEnum):
    BALANCED = "BALANCED"
    SAVER = "SAVER"
    FAST = "FAST"
    CUSTOM = "CUSTOM"


_PRESETS: dict[PreferenceProfile, tuple[float, float, float]] = {
    PreferenceProfile.BALANCED: (0.5, 0.3, 0.2),
    PreferenceProfile.SAVER: (0.7, 0.2, 0.1),
    PreferenceProfile.FAST: (0.2, 0.6, 0.2),
}


@dataclass(frozen=True, slots=True)
class PreferenceWeights:
    profile: PreferenceProfile
    price: float
    duration: float
    stops: float

    def __post_init__(self) -> None:
        for w in (self.price, self.duration, self.stops):
            if w < 0.0 or w > 1.0:
                raise DomainError(
                    "INVALID_WEIGHTS",
                    "Cada peso debe estar en el rango [0, 1].",
                )
        total = self.price + self.duration + self.stops
        if abs(total - 1.0) > 0.001:
            raise DomainError(
                "INVALID_WEIGHTS",
                "La suma de los pesos debe ser 1 (±0.001).",
            )

    @staticmethod
    def from_profile(
        profile: PreferenceProfile,
        price: float | None = None,
        duration: float | None = None,
        stops: float | None = None,
    ) -> "PreferenceWeights":
        if profile == PreferenceProfile.CUSTOM:
            if price is None or duration is None or stops is None:
                raise DomainError(
                    "INVALID_WEIGHTS",
                    "El perfil CUSTOM requiere los pesos price, duration y stops.",
                )
            return PreferenceWeights(
                profile=profile,
                price=float(price),
                duration=float(duration),
                stops=float(stops),
            )
        p, d, s = _PRESETS[profile]
        return PreferenceWeights(profile=profile, price=p, duration=d, stops=s)
