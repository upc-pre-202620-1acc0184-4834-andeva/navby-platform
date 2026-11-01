import random

from src.modules.routing.domain.model.aggregates.airport_graph import AirportGraph
from src.modules.routing.domain.model.entities.airport import Airport
from src.modules.routing.domain.model.value_objects.city_key import CityKey
from src.modules.routing.domain.model.value_objects.coordinates import Coordinates
from src.modules.routing.domain.model.value_objects.edge import Edge
from src.modules.routing.domain.model.value_objects.iata_code import IataCode
from src.modules.routing.domain.services.a_star_search import AStarSearch
from src.modules.routing.domain.services.breadth_first_search import BreadthFirstSearch
from src.modules.routing.domain.services.pair_selector import PairSelector
from src.modules.routing.infrastructure.persistence.graph_provider import get_airport_graph


def _exhaustive_best_minutes(
    graph: AirportGraph,
    origin: IataCode,
    destination: IataCode,
) -> int | None:
    best: float | None = None
    for e1 in graph.neighbors(origin):
        if e1.to == destination:
            cost1 = e1.minutes
            if best is None or cost1 < best:
                best = cost1
            continue
        for e2 in graph.neighbors(e1.to):
            if e2.to == origin:
                continue
            cost2 = e1.minutes + 60.0 + e2.minutes
            if e2.to == destination:
                if best is None or cost2 < best:
                    best = cost2
                continue
            for e3 in graph.neighbors(e2.to):
                if e3.to in (origin, e1.to):
                    continue
                if e3.to == destination:
                    cost3 = cost2 + 60.0 + e3.minutes
                    if best is None or cost3 < best:
                        best = cost3
    return round(best) if best is not None else None


def test_ts26_astar_optimality_on_200_reachable_pairs() -> None:
    graph = get_airport_graph()
    bfs = BreadthFirstSearch()
    astar = AStarSearch()

    rng = random.Random(42)
    all_iatas = sorted(graph.airports.keys())
    reachable_pairs: list[tuple[IataCode, IataCode]] = []
    while len(reachable_pairs) < 200:
        u, v = rng.sample(all_iatas, 2)
        if bfs.min_stops(graph, u, v).reachable:
            reachable_pairs.append((u, v))

    for u, v in reachable_pairs:
        path = astar.fastest_path(graph, u, v)
        assert path is not None
        assert 2 <= len(path.airports) <= 4
        assert len(set(path.airports)) == len(path.airports)
        assert path.airports[0] == u
        assert path.airports[-1] == v
        expected_t_min = _exhaustive_best_minutes(graph, u, v)
        assert path.t_min_minutes == expected_t_min


def test_ts26_astar_stop_penalty_prefers_direct_flight() -> None:
    aaa = IataCode("AAA")
    bbb = IataCode("BBB")
    ccc = IataCode("CCC")
    airports = {
        aaa: Airport(aaa, "KAAA", "A", "A", "C", Coordinates(0.0, 0.0), "UTC"),
        bbb: Airport(bbb, "KBBB", "B", "B", "C", Coordinates(0.0, 2.0), "UTC"),
        ccc: Airport(ccc, "KCCC", "C", "C", "C", Coordinates(0.0, 4.0), "UTC"),
    }
    adjacency = {
        aaa: [
            Edge.from_distance(ccc, 1000.0),
            Edge.from_distance(bbb, 480.0),
        ],
        bbb: [
            Edge.from_distance(ccc, 480.0),
        ],
        ccc: [],
    }
    cities = {
        CityKey("a", "c", 0): [aaa],
        CityKey("b", "c", 0): [bbb],
        CityKey("c", "c", 0): [ccc],
    }
    graph = AirportGraph(airports=airports, adjacency=adjacency, cities=cities)
    astar = AStarSearch()

    route = astar.fastest_path(graph, aaa, ccc)
    assert route is not None
    assert list(route.airports) == [aaa, ccc]
    assert route.t_min_minutes == round(1000.0 / 800.0 * 60.0 + 30.0)


def test_ts26_pair_selector_london_to_lima_and_round_trip_filter() -> None:
    graph = get_airport_graph()
    selector = PairSelector()

    london_cities = [
        c
        for c in graph.search_cities("London", limit=5)
        if c.city == "London" and c.country == "United Kingdom"
    ]
    assert len(london_cities) == 1
    london_iatas = [a.iata for a in london_cities[0].airports]
    assert len(london_iatas) == 5

    selected = selector.select(
        graph,
        origins=london_iatas,
        destinations=[IataCode("LIM")],
        round_trip=False,
        limit=2,
    )
    assert len(selected) == 2
    first, second = selected[0], selected[1]
    key1 = (
        first.min_stops,
        -(graph.out_degree[first.origin] + graph.out_degree[first.destination]),
        first.t_min_minutes,
        first.origin,
        first.destination,
    )
    key2 = (
        second.min_stops,
        -(graph.out_degree[second.origin] + graph.out_degree[second.destination]),
        second.t_min_minutes,
        second.origin,
        second.destination,
    )
    assert key1 <= key2

    aaa = IataCode("AAA")
    bbb = IataCode("BBB")
    airports = {
        aaa: Airport(aaa, "KAAA", "A", "A", "C", Coordinates(0.0, 0.0), "UTC"),
        bbb: Airport(bbb, "KBBB", "B", "B", "C", Coordinates(0.0, 1.0), "UTC"),
    }
    adjacency = {
        aaa: [Edge.from_distance(bbb, 500.0)],
        bbb: [],
    }
    cities = {CityKey("a", "c", 0): [aaa], CityKey("b", "c", 0): [bbb]}
    oneway_graph = AirportGraph(airports=airports, adjacency=adjacency, cities=cities)
    assert selector.select(oneway_graph, [aaa], [bbb], round_trip=False) != []
    assert selector.select(oneway_graph, [aaa], [bbb], round_trip=True) == []
