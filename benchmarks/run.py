import argparse
import csv
import logging
import random
import time
from decimal import Decimal
from pathlib import Path

from src.modules.quotes.domain.model.value_objects.flight_offer import (
    AirlineInfo,
    FlightOffer,
    Leg,
    LegDirection,
    Money,
    Segment,
)
from src.modules.quotes.domain.model.value_objects.preference_weights import (
    PreferenceProfile,
    PreferenceWeights,
)
from src.modules.quotes.domain.services.multicriteria_ranker import MulticriteriaRanker
from src.modules.quotes.domain.services.pareto_filter import ParetoFilter
from src.modules.routing.domain.model.value_objects.iata_code import IataCode
from src.modules.routing.domain.services.a_star_search import AStarSearch
from src.modules.routing.domain.services.breadth_first_search import BreadthFirstSearch
from src.modules.routing.infrastructure.persistence.csv_graph_loader import (
    CsvGraphLoader,
)

logger = logging.getLogger(__name__)


def _generate_synthetic_offers(n: int, rng: random.Random) -> list[FlightOffer]:
    airlines = ("LA", "AA", "AV", "CM", "IB", "DL", "UA", "NH")
    hubs = ("MIA", "PTY", "BOG", "MAD", "LAX", "SCL", "GRU", "JFK")
    offers: list[FlightOffer] = []
    for idx in range(n):
        price = round(rng.uniform(120.0, 2500.0), 2)
        stops = rng.choice((0, 1, 2))
        duration = rng.randint(180, 1800) + stops * 90
        carrier = rng.choice(airlines)
        hub = rng.choice(hubs)
        airports = ("LIM", "HND") if stops == 0 else ("LIM", hub, "HND")
        segments = tuple(
            Segment(
                from_iata=airports[i],
                to_iata=airports[i + 1],
                departure="2026-11-01T08:00:00",
                arrival="2026-11-01T16:00:00",
                flight_number=f"{carrier}{100 + idx % 899}",
                airline_iata=carrier,
            )
            for i in range(len(airports) - 1)
        )
        leg = Leg(
            direction=LegDirection.OUTBOUND,
            departure="2026-11-01T08:00:00",
            arrival="2026-11-01T16:00:00",
            duration_minutes=duration,
            stops=stops,
            segments=segments,
        )
        offers.append(
            FlightOffer(
                offer_id=f"syn_{idx:06d}_{rng.randint(1000, 9999)}",
                price=Money(amount=Decimal(f"{price:.2f}"), currency="USD"),
                duration_minutes=duration,
                stops=stops,
                legs=(leg,),
                airlines=(AirlineInfo(iata=carrier, name=f"Carrier {carrier}", logo=""),),
                deep_link=f"https://example.com/{idx}",
            )
        )
    return offers


def run_benchmarks(
    pairs_count: int = 1000,
    seed: int = 42,
    output_dir: Path | None = None,
    mc_sizes: tuple[int, ...] = (10, 50, 100, 500, 1000),
    mc_repetitions: int = 30,
) -> tuple[Path, Path]:
    out_dir = output_dir or (Path(__file__).resolve().parent / "results")
    out_dir.mkdir(parents=True, exist_ok=True)

    data_dir = Path(__file__).resolve().parent.parent / "data"
    graph = CsvGraphLoader(data_dir).load()
    bfs = BreadthFirstSearch()
    astar = AStarSearch()

    rng = random.Random(seed)
    iata_codes = sorted(graph.airports.keys())
    sampled_pairs: list[tuple[IataCode, IataCode]] = []
    seen_pairs: set[tuple[IataCode, IataCode]] = set()
    while len(sampled_pairs) < pairs_count:
        o = rng.choice(iata_codes)
        d = rng.choice(iata_codes)
        if o != d and (o, d) not in seen_pairs:
            seen_pairs.add((o, d))
            sampled_pairs.append((o, d))

    graph_csv_path = out_dir / "benchmark_graph.csv"
    with graph_csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "origin",
                "destination",
                "reachable",
                "min_stops",
                "t_min_minutes",
                "bfs_ms",
                "astar_ms",
                "astar_nodes_expanded",
            ],
        )
        writer.writeheader()
        for o_iata, d_iata in sampled_pairs:
            t0 = time.perf_counter()
            bfs_res = bfs.min_stops(graph, o_iata, d_iata)
            bfs_ms = (time.perf_counter() - t0) * 1000.0

            t1 = time.perf_counter()
            astar_res = astar.fastest_path(graph, o_iata, d_iata) if bfs_res.reachable else None
            astar_ms = (time.perf_counter() - t1) * 1000.0

            writer.writerow(
                {
                    "origin": o_iata.value,
                    "destination": d_iata.value,
                    "reachable": bfs_res.reachable,
                    "min_stops": bfs_res.min_stops if bfs_res.min_stops is not None else "",
                    "t_min_minutes": (
                        astar_res.t_min_minutes
                        if astar_res is not None and astar_res.t_min_minutes is not None
                        else ""
                    ),
                    "bfs_ms": f"{bfs_ms:.4f}",
                    "astar_ms": f"{astar_ms:.4f}",
                    "astar_nodes_expanded": (
                        astar_res.nodes_expanded if astar_res is not None else 0
                    ),
                }
            )

    mc_csv_path = out_dir / "benchmark_multicriteria.csv"
    pf = ParetoFilter()
    ranker = MulticriteriaRanker()
    weights = PreferenceWeights.from_profile(PreferenceProfile.BALANCED)

    with mc_csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "n_offers",
                "repetition",
                "pareto_size",
                "podium_size",
                "pareto_ms",
                "rank_ms",
                "total_ms",
            ],
        )
        writer.writeheader()
        for n_val in mc_sizes:
            for rep in range(1, mc_repetitions + 1):
                offers = _generate_synthetic_offers(n_val, rng)
                t0 = time.perf_counter()
                front = pf.filter(offers)
                pareto_ms = (time.perf_counter() - t0) * 1000.0

                t1 = time.perf_counter()
                podium = ranker.rank(front, weights)
                rank_ms = (time.perf_counter() - t1) * 1000.0
                total_ms = pareto_ms + rank_ms

                writer.writerow(
                    {
                        "n_offers": n_val,
                        "repetition": rep,
                        "pareto_size": len(front),
                        "podium_size": len(podium),
                        "pareto_ms": f"{pareto_ms:.4f}",
                        "rank_ms": f"{rank_ms:.4f}",
                        "total_ms": f"{total_ms:.4f}",
                    }
                )

    return graph_csv_path, mc_csv_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Navby Benchmark Runner (BFS, A*, Multicriteria)")
    parser.add_argument("--pairs", type=int, default=1000, help="Number of O-D pairs to sample")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to write benchmark CSV files",
    )
    args = parser.parse_args(argv)
    graph_csv, mc_csv = run_benchmarks(
        pairs_count=args.pairs,
        seed=args.seed,
        output_dir=args.output_dir,
    )
    logger.info("Benchmark completed: %s, %s", graph_csv, mc_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
