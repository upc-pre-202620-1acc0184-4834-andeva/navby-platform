from pathlib import Path

from src.modules.routing.domain.model.aggregates.airport_graph import AirportGraph
from src.modules.routing.infrastructure.persistence.csv_graph_loader import CsvGraphLoader

_graph_instance: AirportGraph | None = None


def init_airport_graph(data_dir: Path | str = Path("data")) -> AirportGraph:
    global _graph_instance
    _graph_instance = CsvGraphLoader(data_dir).load()
    return _graph_instance


def get_airport_graph() -> AirportGraph:
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = init_airport_graph()
    return _graph_instance
