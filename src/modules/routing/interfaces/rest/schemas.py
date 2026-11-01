from pydantic import BaseModel, ConfigDict


class CityAirportSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iata: str
    name: str
    lat: float
    lon: float


class CitySchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: str
    city_es: str | None = None
    country: str
    airports: list[CityAirportSchema]


class CitiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cities: list[CitySchema]


class PreviewPairSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: str
    destination: str
    min_stops: int
    t_min_minutes: int


class RouteAirportPointSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iata: str
    lat: float
    lon: float


class BestRouteSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    t_min_minutes: int
    airports: list[RouteAirportPointSchema]


class PreviewTelemetrySchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pairs_evaluated: int
    bfs_ms: float
    astar_ms: float
    astar_nodes_expanded: int


class RoutePreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reachable: bool
    pairs: list[PreviewPairSchema]
    best_route: BestRouteSchema | None
    telemetry: PreviewTelemetrySchema
