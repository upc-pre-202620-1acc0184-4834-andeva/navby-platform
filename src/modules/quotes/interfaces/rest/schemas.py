from pydantic import BaseModel, ConfigDict, Field


class PassengerMixInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adults: int
    children: int = 0
    infants: int = 0


class WeightsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: float
    duration: float
    stops: float


class PreferencesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: str = "BALANCED"
    weights: WeightsInput | None = None


class SearchQuotesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trip_type: str
    origins: list[str]
    destinations: list[str]
    departure_date: str
    return_date: str | None = None
    passengers: PassengerMixInput
    cabin: str
    currency: str
    preferences: PreferencesInput | None = None


class RerankQuotesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: str
    weights: WeightsInput | None = None


class PairQuotedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: str
    destination: str


class PreferencesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: str
    weights: WeightsInput


class MoneyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: str
    currency: str


class AirlineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iata: str
    name: str
    logo: str


class SegmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_iata: str = Field(serialization_alias="from")
    to_iata: str = Field(serialization_alias="to")
    departure: str
    arrival: str
    flight_number: str
    airline: str


class LegResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: str
    departure: str
    arrival: str
    duration_minutes: int
    stops: int
    segments: list[SegmentResponse]


class AirportGeoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iata: str
    lat: float
    lon: float
    timezone: str


class PodiumOfferResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    offer_id: str
    score: float
    match_pct: int
    price: MoneyResponse
    duration_minutes: int
    extra_minutes_vs_t_min: int
    stops: int
    airlines: list[AirlineResponse]
    legs: list[LegResponse]
    airports: list[AirportGeoResponse]
    deep_link: str


class PodiumResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search_id: str
    expires_at: str
    credits_charged: int
    credits_remaining: int
    partial: bool
    pairs_quoted: list[PairQuotedResponse]
    t_min_minutes: int
    offers_received: int
    pareto_size: int
    preferences: PreferencesResponse
    price_disclaimer: str
    podium: list[PodiumOfferResponse]
