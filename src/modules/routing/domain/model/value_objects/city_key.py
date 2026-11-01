from dataclasses import dataclass


@dataclass(frozen=True, slots=True, order=True)
class CityKey:
    city_norm: str
    country_norm: str
    cluster_id: int = 0
