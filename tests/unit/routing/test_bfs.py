from src.modules.routing.domain.model.aggregates.airport_graph import AirportGraph
from src.modules.routing.domain.model.entities.airport import Airport
from src.modules.routing.domain.model.value_objects.city_key import CityKey
from src.modules.routing.domain.model.value_objects.coordinates import Coordinates
from src.modules.routing.domain.model.value_objects.edge import Edge
from src.modules.routing.domain.model.value_objects.iata_code import IataCode
from src.modules.routing.domain.services.breadth_first_search import BreadthFirstSearch
from src.modules.routing.infrastructure.persistence.graph_provider import get_airport_graph


def test_ts25_bfs_min_stops_on_real_graph() -> None:
    graph = get_airport_graph()
    bfs = BreadthFirstSearch()

    r_lim_mia = bfs.min_stops(graph, IataCode("LIM"), IataCode("MIA"))
    assert r_lim_mia.reachable is True
    assert r_lim_mia.min_stops == 0

    r_lim_nrt = bfs.min_stops(graph, IataCode("LIM"), IataCode("NRT"))
    assert r_lim_nrt.reachable is True
    assert r_lim_nrt.min_stops in (1, 2)


def test_ts25_bfs_depth_limit_3_legs_max_2_stops() -> None:
    codes = [IataCode(c) for c in ("AAA", "BBB", "CCC", "DDD", "EEE")]
    airports = {
        code: Airport(
            iata=code,
            icao=f"K{code.value}",
            name=f"Airport {code.value}",
            city=f"City {code.value}",
            country="Testland",
            coordinates=Coordinates(0.0, float(idx)),
            timezone="UTC",
        )
        for idx, code in enumerate(codes)
    }
    adjacency = {
        codes[0]: [Edge.from_distance(codes[1], 500.0)],
        codes[1]: [Edge.from_distance(codes[2], 500.0)],
        codes[2]: [Edge.from_distance(codes[3], 500.0)],
        codes[3]: [Edge.from_distance(codes[4], 500.0)],
        codes[4]: [],
    }
    cities = {CityKey(f"city {c.value.lower()}", "testland", 0): [c] for c in codes}
    graph = AirportGraph(airports=airports, adjacency=adjacency, cities=cities)
    bfs = BreadthFirstSearch()

    res_2_stops = bfs.min_stops(graph, codes[0], codes[3])
    assert res_2_stops.reachable is True
    assert res_2_stops.min_stops == 2

    res_3_stops = bfs.min_stops(graph, codes[0], codes[4])
    assert res_3_stops.reachable is False
    assert res_3_stops.min_stops is None
