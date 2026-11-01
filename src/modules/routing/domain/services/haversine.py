import math

from src.modules.routing.domain.model.value_objects.coordinates import Coordinates


class Haversine:
    EARTH_RADIUS_KM = 6371.0

    @classmethod
    def distance_km(cls, a: Coordinates, b: Coordinates) -> float:
        lat1 = math.radians(a.lat)
        lat2 = math.radians(b.lat)
        dlat = math.radians(b.lat - a.lat)
        dlon = math.radians(b.lon - a.lon)

        sin_dlat = math.sin(dlat / 2.0)
        sin_dlon = math.sin(dlon / 2.0)
        h = sin_dlat * sin_dlat + math.cos(lat1) * math.cos(lat2) * sin_dlon * sin_dlon
        c = 2.0 * math.atan2(math.sqrt(h), math.sqrt(max(0.0, 1.0 - h)))
        return cls.EARTH_RADIUS_KM * c
