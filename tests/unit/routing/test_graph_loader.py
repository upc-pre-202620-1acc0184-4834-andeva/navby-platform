import csv
import shutil
from pathlib import Path

import pytest

from src.modules.routing.domain.model.value_objects.iata_code import IataCode
from src.modules.routing.infrastructure.persistence.csv_graph_loader import (
    CsvGraphLoader,
    GraphLoadError,
)

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def test_ts24_csv_aliases_and_overrides_match_airports_csv() -> None:
    airports_cities: set[tuple[str, str]] = set()
    airports_iatas: set[str] = set()
    with (DATA_DIR / "airports.csv").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            airports_cities.add((row["city"], row["country"]))
            airports_iatas.add(row["iata"])

    with (DATA_DIR / "airport_city_overrides.csv").open(encoding="utf-8") as f:
        overrides = list(csv.DictReader(f))
    assert len(overrides) == 1
    for row in overrides:
        assert row["iata"] in airports_iatas
        assert (row["city"], row["country"]) in airports_cities

    with (DATA_DIR / "city_aliases_es.csv").open(encoding="utf-8") as f:
        aliases = list(csv.DictReader(f))
    assert len(aliases) == 119
    for row in aliases:
        assert (row["city"], row["country"]) in airports_cities


def test_ts24_load_graph_counts_edges_overrides_and_cities() -> None:
    graph = CsvGraphLoader(DATA_DIR).load()

    assert len(graph.airports) == 3354
    total_edges = sum(len(edges) for edges in graph.adjacency.values())
    assert total_edges == 37326

    lim = graph.airport(IataCode("LIM"))
    assert lim is not None
    assert lim.city == "Lima"
    assert lim.country == "Peru"
    assert graph.out_degree[IataCode("LIM")] == len(graph.neighbors(IataCode("LIM")))

    for edges in graph.adjacency.values():
        for edge in edges[:5]:
            expected_minutes = edge.distance_km / 800.0 * 60.0 + 30.0
            assert abs(edge.minutes - expected_minutes) < 1e-9

    ny_results = graph.search_cities("Nueva York", limit=5)
    assert len(ny_results) >= 1
    ny = next(c for c in ny_results if c.city == "New York" and c.country == "United States")
    ny_iatas = {a.iata.value for a in ny.airports}
    assert {"JFK", "LGA", "EWR"}.issubset(ny_iatas)

    columbus_results = [
        c for c in graph.search_cities("Columbus", limit=10) if c.city == "Columbus"
    ]
    assert len(columbus_results) >= 2

    counts_by_size: dict[int, int] = {}
    for iata_list in graph.cities.values():
        sz = len(iata_list)
        counts_by_size[sz] = counts_by_size.get(sz, 0) + 1
    assert counts_by_size == {1: 3244, 2: 48, 3: 3, 5: 1}
    assert sum(k * v for k, v in counts_by_size.items()) == 3354


def test_ts24_inconsistent_or_missing_csv_raises_error(tmp_path: Path) -> None:
    with pytest.raises(GraphLoadError):
        CsvGraphLoader(tmp_path).load()

    for fname in (
        "airports.csv",
        "routes_unique.csv",
        "airport_city_overrides.csv",
        "city_aliases_es.csv",
    ):
        shutil.copy(DATA_DIR / fname, tmp_path / fname)

    airports_copy = tmp_path / "airports.csv"
    lines = airports_copy.read_text(encoding="utf-8").splitlines()
    airports_copy.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")

    with pytest.raises(GraphLoadError):
        CsvGraphLoader(tmp_path).load()
