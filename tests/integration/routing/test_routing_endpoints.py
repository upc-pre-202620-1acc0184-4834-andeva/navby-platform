from httpx import ASGITransport, AsyncClient

from src.main import create_app


async def test_ts12_routing_cities_search_alias_name_iata_and_normalization() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for query in ("tok", "TOKYO", "hnd"):
            resp = await client.get("/api/v1/routing/cities", params={"q": query})
            assert resp.status_code == 200
            cities = resp.json()["cities"]
            tokyo = next(
                (c for c in cities if c["city"] == "Tokyo" and c["country"] == "Japan"),
                None,
            )
            assert tokyo is not None
            assert tokyo["city_es"] == "Tokio"
            iatas = {a["iata"] for a in tokyo["airports"]}
            assert {"HND", "NRT"}.issubset(iatas)
            for ap in tokyo["airports"]:
                assert isinstance(ap["lat"], float)
                assert isinstance(ap["lon"], float)
                assert isinstance(ap["name"], str)

        r_bog = await client.get("/api/v1/routing/cities", params={"q": "bogota"})
        assert r_bog.status_code == 200
        bog = next(
            (c for c in r_bog.json()["cities"] if c["city"] == "Bogota"),
            None,
        )
        assert bog is not None
        assert bog["city_es"] == "Bogotá"


async def test_ts12_routing_cities_metropolitan_grouping_and_validation() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_ny = await client.get("/api/v1/routing/cities", params={"q": "New York"})
        assert r_ny.status_code == 200
        ny = next(
            c
            for c in r_ny.json()["cities"]
            if c["city"] == "New York" and c["country"] == "United States"
        )
        assert {"JFK", "LGA", "EWR"}.issubset({a["iata"] for a in ny["airports"]})

        r_col = await client.get("/api/v1/routing/cities", params={"q": "Columbus", "limit": 10})
        assert r_col.status_code == 200
        columbus_entries = [c for c in r_col.json()["cities"] if c["city"] == "Columbus"]
        assert len(columbus_entries) >= 2

        r_short = await client.get("/api/v1/routing/cities", params={"q": "a"})
        assert r_short.status_code == 422
        assert r_short.json()["code"] == "VALIDATION_ERROR"

        r_limit = await client.get("/api/v1/routing/cities", params={"q": "lim", "limit": 21})
        assert r_limit.status_code == 422
        assert r_limit.json()["code"] == "VALIDATION_ERROR"


async def test_ts13_routing_preview_reachable_and_round_trip() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.get(
            "/api/v1/routing/preview",
            params={"origins": "LIM", "destinations": "HND,NRT", "trip_type": "ONE_WAY"},
        )
        assert r1.status_code == 200
        b1 = r1.json()
        assert b1["reachable"] is True
        assert 1 <= len(b1["pairs"]) <= 2
        assert b1["best_route"] is not None
        assert len(b1["best_route"]["airports"]) >= 2
        assert b1["best_route"]["airports"][0]["iata"] == "LIM"
        assert b1["telemetry"]["pairs_evaluated"] == 2
        assert b1["telemetry"]["bfs_ms"] >= 0.0
        assert b1["telemetry"]["astar_ms"] >= 0.0
        assert b1["telemetry"]["astar_nodes_expanded"] > 0

        r_rt = await client.get(
            "/api/v1/routing/preview",
            params={"origins": "LIM", "destinations": "HND,NRT", "trip_type": "ROUND_TRIP"},
        )
        assert r_rt.status_code == 200
        b_rt = r_rt.json()
        assert b_rt["reachable"] is True
        assert b_rt["pairs"][0]["t_min_minutes"] > b1["pairs"][0]["t_min_minutes"]


async def test_ts13_routing_preview_unreachable_and_invalid_inputs() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_unreach = await client.get(
            "/api/v1/routing/preview",
            params={"origins": "IPC", "destinations": "FNJ"},
        )
        assert r_unreach.status_code == 200
        b_unreach = r_unreach.json()
        assert b_unreach["reachable"] is False
        assert b_unreach["pairs"] == []
        assert b_unreach["best_route"] is None

        r_404 = await client.get(
            "/api/v1/routing/preview",
            params={"origins": "ZZZ", "destinations": "LIM"},
        )
        assert r_404.status_code == 404
        assert r_404.json()["code"] == "AIRPORT_NOT_FOUND"

        r_overlap = await client.get(
            "/api/v1/routing/preview",
            params={"origins": "LIM,MIA", "destinations": "MIA,JFK"},
        )
        assert r_overlap.status_code == 422
        assert r_overlap.json()["code"] == "VALIDATION_ERROR"

        r_too_many = await client.get(
            "/api/v1/routing/preview",
            params={"origins": "LHR,LGW,STN,LTN,LCY,MAN", "destinations": "LIM"},
        )
        assert r_too_many.status_code == 422
        assert r_too_many.json()["code"] == "VALIDATION_ERROR"
