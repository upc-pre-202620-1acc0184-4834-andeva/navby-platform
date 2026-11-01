import unicodedata

from src.modules.routing.domain.model.entities.airport import Airport
from src.modules.routing.domain.model.value_objects.city import City
from src.modules.routing.domain.model.value_objects.city_key import CityKey
from src.modules.routing.domain.model.value_objects.edge import Edge
from src.modules.routing.domain.model.value_objects.iata_code import IataCode
from src.shared.domain.aggregate_root import AggregateRoot


def normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.casefold().strip()


class AirportGraph(AggregateRoot):
    def __init__(
        self,
        airports: dict[IataCode, Airport],
        adjacency: dict[IataCode, list[Edge]],
        cities: dict[CityKey, list[IataCode]],
        city_aliases_es: dict[tuple[str, str], str] | None = None,
    ) -> None:
        super().__init__()
        self.airports = airports
        self.adjacency = adjacency
        self.cities = cities
        self.out_degree: dict[IataCode, int] = {
            iata: len(adjacency.get(iata, [])) for iata in airports
        }
        self._aliases_es: dict[tuple[str, str], str] = city_aliases_es or {}
        self._city_objects: dict[CityKey, City] = {}
        for key, iatas in self.cities.items():
            airport_objs = tuple(self.airports[code] for code in iatas)
            first = airport_objs[0]
            alias_es = self._aliases_es.get((key.city_norm, key.country_norm))
            self._city_objects[key] = City(
                city=first.city,
                city_es=alias_es,
                country=first.country,
                airports=airport_objs,
            )

    def airport(self, iata: IataCode) -> Airport | None:
        return self.airports.get(iata)

    def neighbors(self, iata: IataCode) -> list[Edge]:
        return self.adjacency.get(iata, [])

    def search_cities(self, text: str, limit: int = 10) -> list[City]:
        query = normalize_text(text)
        if not query or limit <= 0:
            return []

        matches: list[tuple[int, int, str, City]] = []
        for city_obj in self._city_objects.values():
            city_norm = normalize_text(city_obj.city)
            alias_norm = normalize_text(city_obj.city_es) if city_obj.city_es else ""

            matched = False
            priority = 3
            if any(normalize_text(a.iata.value).startswith(query) for a in city_obj.airports):
                matched = True
                if any(normalize_text(a.iata.value) == query for a in city_obj.airports):
                    priority = 0
                else:
                    priority = 1
            if city_norm.startswith(query) or (alias_norm and alias_norm.startswith(query)):
                matched = True
                if city_norm == query or alias_norm == query:
                    priority = min(priority, 0)
                else:
                    priority = min(priority, 1)
            if not matched and any(
                normalize_text(a.name).startswith(query) for a in city_obj.airports
            ):
                matched = True
                priority = 2

            if matched:
                total_out_deg = sum(self.out_degree.get(a.iata, 0) for a in city_obj.airports)
                matches.append((priority, -total_out_deg, city_obj.city, city_obj))

        matches.sort(key=lambda item: (item[0], item[1], item[2]))
        return [item[3] for item in matches[:limit]]
