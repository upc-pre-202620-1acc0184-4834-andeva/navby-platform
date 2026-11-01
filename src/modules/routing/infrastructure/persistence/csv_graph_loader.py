import csv
import logging
from collections import defaultdict
from pathlib import Path

from src.modules.routing.domain.model.aggregates.airport_graph import (
    AirportGraph,
    normalize_text,
)
from src.modules.routing.domain.model.entities.airport import Airport
from src.modules.routing.domain.model.value_objects.city_key import CityKey
from src.modules.routing.domain.model.value_objects.coordinates import Coordinates
from src.modules.routing.domain.model.value_objects.edge import Edge
from src.modules.routing.domain.model.value_objects.iata_code import IataCode
from src.modules.routing.domain.services.haversine import Haversine

logger = logging.getLogger(__name__)


class GraphLoadError(RuntimeError):
    pass


class CsvGraphLoader:
    EXPECTED_AIRPORTS = 3354
    EXPECTED_EDGES = 37326
    EXPECTED_ALIASES = 119
    MAX_CITY_CLUSTER_DISTANCE_KM = 80.0

    def __init__(self, data_dir: Path | str = Path("data")) -> None:
        self._data_dir = Path(data_dir)

    def load(self) -> AirportGraph:
        airports_file = self._data_dir / "airports.csv"
        routes_file = self._data_dir / "routes_unique.csv"
        overrides_file = self._data_dir / "airport_city_overrides.csv"
        aliases_file = self._data_dir / "city_aliases_es.csv"

        for fpath in (airports_file, routes_file, overrides_file, aliases_file):
            if not fpath.exists():
                msg = f"Missing required graph dataset file: {fpath}"
                logger.critical(msg)
                raise GraphLoadError(msg)

        overrides: dict[str, tuple[str, str]] = {}
        with overrides_file.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                overrides[row["iata"].strip()] = (row["city"].strip(), row["country"].strip())

        aliases_es: dict[tuple[str, str], str] = {}
        alias_count = 0
        with aliases_file.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                alias_count += 1
                c_norm = normalize_text(row["city"])
                country_norm = normalize_text(row["country"])
                aliases_es[(c_norm, country_norm)] = row["alias_es"].strip()

        if alias_count != self.EXPECTED_ALIASES:
            msg = f"Expected {self.EXPECTED_ALIASES} city aliases, found {alias_count}"
            logger.critical(msg)
            raise GraphLoadError(msg)

        airports: dict[IataCode, Airport] = {}
        with airports_file.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                iata_str = row["iata"].strip()
                iata = IataCode(iata_str)
                city, country = overrides.get(
                    iata_str, (row["city"].strip(), row["country"].strip())
                )
                airport = Airport(
                    iata=iata,
                    icao=row["icao"].strip(),
                    name=row["name"].strip(),
                    city=city,
                    country=country,
                    coordinates=Coordinates(
                        lat=float(row["latitude"]),
                        lon=float(row["longitude"]),
                    ),
                    timezone=row["tz_database_timezone"].strip(),
                )
                airports[iata] = airport

        if len(airports) != self.EXPECTED_AIRPORTS:
            msg = f"Expected {self.EXPECTED_AIRPORTS} airports, loaded {len(airports)}"
            logger.critical(msg)
            raise GraphLoadError(msg)

        adjacency: dict[IataCode, list[Edge]] = defaultdict(list)
        edge_count = 0
        with routes_file.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                src = IataCode(row["source_airport"].strip())
                dst = IataCode(row["destination_airport"].strip())
                if src not in airports or dst not in airports:
                    msg = f"Route references unknown airport: {src} -> {dst}"
                    logger.critical(msg)
                    raise GraphLoadError(msg)
                dist = float(row["distance_km"])
                adjacency[src].append(Edge.from_distance(to=dst, distance_km=dist))
                edge_count += 1

        if edge_count != self.EXPECTED_EDGES:
            msg = f"Expected {self.EXPECTED_EDGES} edges, loaded {edge_count}"
            logger.critical(msg)
            raise GraphLoadError(msg)

        cities = self._cluster_cities(airports)
        return AirportGraph(
            airports=airports,
            adjacency=dict(adjacency),
            cities=cities,
            city_aliases_es=aliases_es,
        )

    def _cluster_cities(self, airports: dict[IataCode, Airport]) -> dict[CityKey, list[IataCode]]:
        by_name_country: dict[tuple[str, str], list[Airport]] = defaultdict(list)
        for airport in airports.values():
            key = (normalize_text(airport.city), normalize_text(airport.country))
            by_name_country[key].append(airport)

        cities: dict[CityKey, list[IataCode]] = {}
        for (city_norm, country_norm), group in by_name_country.items():
            group_sorted = sorted(group, key=lambda a: a.iata.value)
            visited: set[IataCode] = set()
            clusters: list[list[Airport]] = []
            for start in group_sorted:
                if start.iata in visited:
                    continue
                visited.add(start.iata)
                cluster = [start]
                queue = [start]
                while queue:
                    curr = queue.pop(0)
                    for other in group_sorted:
                        if other.iata not in visited and (
                            Haversine.distance_km(curr.coordinates, other.coordinates)
                            < self.MAX_CITY_CLUSTER_DISTANCE_KM
                        ):
                            visited.add(other.iata)
                            cluster.append(other)
                            queue.append(other)
                cluster.sort(key=lambda a: a.iata.value)
                clusters.append(cluster)

            for idx, cluster in enumerate(clusters):
                city_key = CityKey(
                    city_norm=city_norm,
                    country_norm=country_norm,
                    cluster_id=idx,
                )
                cities[city_key] = [a.iata for a in cluster]
        return cities
