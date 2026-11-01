import csv
from pathlib import Path

from benchmarks.run import run_benchmarks


def test_ts37_benchmark_script_deterministic_and_csv_outputs(tmp_path: Path) -> None:
    out_dir_1 = tmp_path / "run1"
    out_dir_2 = tmp_path / "run2"

    graph_csv_1, mc_csv_1 = run_benchmarks(
        pairs_count=25,
        seed=42,
        output_dir=out_dir_1,
        mc_sizes=(10, 50, 100, 500, 1000),
        mc_repetitions=30,
    )
    graph_csv_2, _ = run_benchmarks(
        pairs_count=25,
        seed=42,
        output_dir=out_dir_2,
        mc_sizes=(10,),
        mc_repetitions=2,
    )

    rows_1 = list(csv.DictReader(graph_csv_1.read_text(encoding="utf-8").splitlines()))
    rows_2 = list(csv.DictReader(graph_csv_2.read_text(encoding="utf-8").splitlines()))
    assert len(rows_1) == 25
    assert [(r["origin"], r["destination"]) for r in rows_1] == [
        (r["origin"], r["destination"]) for r in rows_2
    ]
    assert {
        "origin",
        "destination",
        "bfs_ms",
        "astar_ms",
        "astar_nodes_expanded",
        "min_stops",
    } <= set(rows_1[0].keys())

    mc_rows = list(csv.DictReader(mc_csv_1.read_text(encoding="utf-8").splitlines()))
    assert len(mc_rows) == 5 * 30
    sizes_seen = {int(r["n_offers"]) for r in mc_rows}
    assert sizes_seen == {10, 50, 100, 500, 1000}
