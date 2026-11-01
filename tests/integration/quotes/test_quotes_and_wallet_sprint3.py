import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from src.main import build_outbox_relay, create_app
from src.modules.iam.application.acl.ports.email_sender import EmailSender
from src.modules.iam.interfaces.rest.router import get_email_sender
from src.modules.quotes.application.acl.ports.flight_offers_provider import (
    FlightOffersProvider,
)
from src.modules.quotes.domain.model.value_objects.flight_offer import FlightOffer
from src.modules.quotes.domain.model.value_objects.search_criteria import (
    AirportPair,
    SearchCriteria,
)
from src.modules.quotes.infrastructure.adapters.mock_flight_offers_provider import (
    MockFlightOffersProvider,
)
from src.modules.quotes.interfaces.rest.router import get_flight_offers_provider
from src.shared.application.application_error import ApplicationError
from src.shared.application.result import Result
from src.shared.infrastructure.database import get_session_factory
from src.shared.infrastructure.redis_client import get_redis_client

LIMA_TZ = ZoneInfo("America/Lima")


class SilentEmailSender(EmailSender):
    def __init__(self) -> None:
        self.codes: list[str] = []

    async def send_verification_code(self, email: str, code: str) -> None:
        self.codes.append(code)

    async def send_password_reset(self, email: str, link: str) -> None:
        pass


class ConfigurableOffersProvider(FlightOffersProvider):
    def __init__(self) -> None:
        self.delegate = MockFlightOffersProvider()
        self.calls: list[tuple[str, str]] = []
        self.fail_pairs: set[tuple[str, str]] = set()
        self.empty_pairs: set[tuple[str, str]] = set()
        self.delay_seconds: float = 0.0

    async def fetch_offers(
        self, pair: AirportPair, criteria: SearchCriteria
    ) -> Result[list[FlightOffer]]:
        self.calls.append((pair.origin, pair.destination))
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        if (pair.origin, pair.destination) in self.fail_pairs:
            return Result.failure(
                ApplicationError(code="PROVIDER_UNAVAILABLE", message="Upstream failed")
            )
        if (pair.origin, pair.destination) in self.empty_pairs:
            return Result.success([])
        return await self.delegate.fetch_offers(pair, criteria)


@pytest.fixture
async def clean_sprint3_state() -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        await session.execute(text("DELETE FROM shared.outbox_events"))
        await session.execute(text("DELETE FROM iam.refresh_tokens"))
        await session.execute(text("DELETE FROM iam.users"))
        await session.execute(text("DELETE FROM billing.credit_transactions"))
        await session.execute(text("DELETE FROM billing.credit_wallets"))
        await session.execute(text("DELETE FROM billing.credit_orders"))
        await session.execute(text("DELETE FROM itineraries.saved_itineraries"))
        await session.commit()

    redis = get_redis_client()
    keys = await redis.keys("navby:*")
    if keys:
        await redis.delete(*keys)
    await redis.aclose()


async def _register_and_verify(
    client: AsyncClient, sender: SilentEmailSender, email: str = "traveler@mail.com"
) -> tuple[UUID, str]:
    r_reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Viajar2026",
            "full_name": "Traveler",
            "accept_terms": True,
        },
    )
    user_id = UUID(r_reg.json()["user_id"])
    r_ver = await client.post(
        "/api/v1/auth/verify-email",
        json={"email": email, "code": sender.codes[-1]},
    )
    token = r_ver.json()["access_token"]
    session_factory = get_session_factory()
    relay = build_outbox_relay(session_factory)
    await relay.process_pending_batch()
    return user_id, token


async def test_ts14_ts15_ts16_quotes_search_cache_rerank_and_get(
    clean_sprint3_state: None,
) -> None:
    app = create_app()
    sender = SilentEmailSender()
    provider = ConfigurableOffersProvider()
    app.dependency_overrides[get_email_sender] = lambda: sender
    app.dependency_overrides[get_flight_offers_provider] = lambda: provider
    transport = ASGITransport(app=app)

    tomorrow = (datetime.now(UTC).astimezone(LIMA_TZ).date() + timedelta(days=10)).isoformat()
    ret_date = (datetime.now(UTC).astimezone(LIMA_TZ).date() + timedelta(days=20)).isoformat()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id, token = await _register_and_verify(client, sender)
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Search without cache -> charges 5 credits, stores session & pair cache
        r_search = await client.post(
            "/api/v1/quotes/search",
            headers=headers,
            json={
                "trip_type": "ROUND_TRIP",
                "origins": ["LIM"],
                "destinations": ["MIA"],
                "departure_date": tomorrow,
                "return_date": ret_date,
                "passengers": {"adults": 1, "children": 0, "infants": 0},
                "cabin": "ECONOMY",
                "currency": "USD",
                "preferences": {"profile": "BALANCED"},
            },
        )
        assert r_search.status_code == 200
        body = r_search.json()
        search_id = body["search_id"]
        assert search_id.startswith("srch_")
        assert body["credits_charged"] == 5
        assert body["credits_remaining"] == 5
        assert body["partial"] is False
        assert 1 <= len(body["podium"]) <= 3
        assert "price_disclaimer" in body
        assert len(provider.calls) == 1

        # Verify SEARCH_DEBIT in Postgres
        session_factory = get_session_factory()
        async with session_factory() as session:
            tx_row = (
                await session.execute(
                    text(
                        "SELECT type, free_delta, paid_delta FROM billing.credit_transactions "
                        "WHERE user_id = :u AND reference_id = :ref"
                    ),
                    {"u": user_id, "ref": search_id},
                )
            ).first()
            assert tx_row == ("SEARCH_DEBIT", -5, 0)

        # Verify Redis TTL <= 1800
        redis = get_redis_client()
        ttl_before = await redis.ttl(f"navby:quotes:search:{search_id}")
        await redis.aclose()
        assert 0 < ttl_before <= 1800

        # 2. Search again with everything in cache -> credits_charged = 0, no new provider calls
        r_cached = await client.post(
            "/api/v1/quotes/search",
            headers=headers,
            json={
                "trip_type": "ROUND_TRIP",
                "origins": ["LIM"],
                "destinations": ["MIA"],
                "departure_date": tomorrow,
                "return_date": ret_date,
                "passengers": {"adults": 1, "children": 0, "infants": 0},
                "cabin": "ECONOMY",
                "currency": "USD",
            },
        )
        assert r_cached.status_code == 200
        assert r_cached.json()["credits_charged"] == 0
        assert len(provider.calls) == 1

        # 3. TS-15 Rerank with SAVER -> credits_charged = 0, same expires_at, KEEPTTL
        r_rank = await client.post(
            f"/api/v1/quotes/{search_id}/rank",
            headers=headers,
            json={"profile": "SAVER"},
        )
        assert r_rank.status_code == 200
        rank_body = r_rank.json()
        assert rank_body["credits_charged"] == 0
        assert rank_body["expires_at"] == body["expires_at"]
        assert rank_body["preferences"]["profile"] == "SAVER"

        # Invalid weights on rerank -> 422 INVALID_WEIGHTS
        r_bad_w = await client.post(
            f"/api/v1/quotes/{search_id}/rank",
            headers=headers,
            json={"profile": "CUSTOM", "weights": {"price": 0.8, "duration": 0.2, "stops": 0.1}},
        )
        assert r_bad_w.status_code == 422
        assert r_bad_w.json()["code"] == "INVALID_WEIGHTS"

        # 4. TS-16 GET /quotes/{search_id} -> returns last weights (SAVER) and credits_charged = 0
        r_get = await client.get(f"/api/v1/quotes/{search_id}", headers=headers)
        assert r_get.status_code == 200
        assert r_get.json()["preferences"]["profile"] == "SAVER"
        assert r_get.json()["credits_charged"] == 0

        # Non-existent or foreign search -> 404 SEARCH_NOT_FOUND
        r_404 = await client.get("/api/v1/quotes/srch_01J9Z000000000000000000000", headers=headers)
        assert r_404.status_code == 404
        assert r_404.json()["code"] == "SEARCH_NOT_FOUND"


async def test_ts14_refunds_partial_rejections_and_concurrency_lock(
    clean_sprint3_state: None,
) -> None:
    app = create_app()
    sender = SilentEmailSender()
    provider = ConfigurableOffersProvider()
    app.dependency_overrides[get_email_sender] = lambda: sender
    app.dependency_overrides[get_flight_offers_provider] = lambda: provider
    transport = ASGITransport(app=app)

    dep_date = (datetime.now(UTC).astimezone(LIMA_TZ).date() + timedelta(days=15)).isoformat()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id, token = await _register_and_verify(client, sender, "refunds@mail.com")
        headers = {"Authorization": f"Bearer {token}"}

        # All provider calls fail and no cache -> 503 PROVIDER_UNAVAILABLE + SEARCH_REFUND
        provider.fail_pairs = {("LIM", "MAD")}
        r_fail = await client.post(
            "/api/v1/quotes/search",
            headers=headers,
            json={
                "trip_type": "ONE_WAY",
                "origins": ["LIM"],
                "destinations": ["MAD"],
                "departure_date": dep_date,
                "passengers": {"adults": 1, "children": 0, "infants": 0},
                "cabin": "ECONOMY",
                "currency": "USD",
            },
        )
        assert r_fail.status_code == 503
        assert r_fail.json()["code"] == "PROVIDER_UNAVAILABLE"

        session_factory = get_session_factory()
        async with session_factory() as session:
            ref_count = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM billing.credit_transactions "
                        "WHERE user_id = :u AND type = 'SEARCH_REFUND'"
                    ),
                    {"u": user_id},
                )
            ).scalar_one()
            assert ref_count == 1

        # Empty offers -> 200 with podium = [], credits_charged = 0, SEARCH_REFUND
        provider.fail_pairs.clear()
        provider.empty_pairs = {("LIM", "BOG")}
        r_empty = await client.post(
            "/api/v1/quotes/search",
            headers=headers,
            json={
                "trip_type": "ONE_WAY",
                "origins": ["LIM"],
                "destinations": ["BOG"],
                "departure_date": dep_date,
                "passengers": {"adults": 1, "children": 0, "infants": 0},
                "cabin": "ECONOMY",
                "currency": "USD",
            },
        )
        assert r_empty.status_code == 200
        assert r_empty.json()["podium"] == []
        assert r_empty.json()["credits_charged"] == 0

        # 1 of 2 pairs fails (LIM -> HND, NRT) -> 200 with partial = true, credits_charged = 5
        provider.empty_pairs.clear()
        provider.fail_pairs = {("LIM", "NRT")}
        r_partial = await client.post(
            "/api/v1/quotes/search",
            headers=headers,
            json={
                "trip_type": "ONE_WAY",
                "origins": ["LIM"],
                "destinations": ["HND", "NRT"],
                "departure_date": dep_date,
                "passengers": {"adults": 1, "children": 0, "infants": 0},
                "cabin": "ECONOMY",
                "currency": "USD",
            },
        )
        assert r_partial.status_code == 200
        assert r_partial.json()["partial"] is True
        assert r_partial.json()["credits_charged"] == 5

        # Concurrent double submit -> one 200, one 409 SEARCH_IN_PROGRESS
        provider.fail_pairs.clear()
        provider.delay_seconds = 0.15
        dep_date_2 = (datetime.now(UTC).astimezone(LIMA_TZ).date() + timedelta(days=25)).isoformat()
        payload_conc = {
            "trip_type": "ONE_WAY",
            "origins": ["LIM"],
            "destinations": ["SCL"],
            "departure_date": dep_date_2,
            "passengers": {"adults": 1, "children": 0, "infants": 0},
            "cabin": "ECONOMY",
            "currency": "USD",
        }
        res_a, res_b = await asyncio.gather(
            client.post("/api/v1/quotes/search", headers=headers, json=payload_conc),
            client.post("/api/v1/quotes/search", headers=headers, json=payload_conc),
        )
        statuses = sorted([res_a.status_code, res_b.status_code])
        assert statuses == [200, 409]
        provider.delay_seconds = 0.0

        # Now user has 0 credits left; set wallet to 3 credits -> 402 INSUFFICIENT_CREDITS
        async with session_factory() as session:
            await session.execute(
                text(
                    "UPDATE billing.credit_wallets SET free_credits = 3, paid_credits = 0 "
                    "WHERE user_id = :u"
                ),
                {"u": user_id},
            )
            await session.commit()

        r_402 = await client.post(
            "/api/v1/quotes/search",
            headers=headers,
            json={
                "trip_type": "ONE_WAY",
                "origins": ["LIM"],
                "destinations": ["EZE"],
                "departure_date": dep_date_2,
                "passengers": {"adults": 1, "children": 0, "infants": 0},
                "cabin": "ECONOMY",
                "currency": "USD",
            },
        )
        assert r_402.status_code == 402
        assert r_402.json()["code"] == "INSUFFICIENT_CREDITS"


async def test_ts17_get_billing_wallet_projected_and_reset_at(
    clean_sprint3_state: None,
) -> None:
    app = create_app()
    sender = SilentEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register and verify without running outbox relay -> lazy projection
        r_reg = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "wallet@mail.com",
                "password": "Viajar2026",
                "full_name": "Wallet User",
                "accept_terms": True,
            },
        )
        user_id = UUID(r_reg.json()["user_id"])
        r_ver = await client.post(
            "/api/v1/auth/verify-email",
            json={"email": "wallet@mail.com", "code": sender.codes[-1]},
        )
        token = r_ver.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        r_w1 = await client.get("/api/v1/billing/wallet", headers=headers)
        assert r_w1.status_code == 200
        w1 = r_w1.json()
        assert w1["free_credits"] == 10
        assert w1["paid_credits"] == 0
        assert w1["total_credits"] == 10
        assert w1["searches_available"] == 2
        assert w1["free_credits_reset_at"].endswith("T05:00:00Z")

        session_factory = get_session_factory()
        async with session_factory() as session:
            count = (
                await session.execute(
                    text("SELECT count(*) FROM billing.credit_wallets WHERE user_id = :u"),
                    {"u": user_id},
                )
            ).scalar_one()
            assert count == 0

            # Insert wallet with yesterday's date and free_credits = 0
            yesterday_lima = datetime.now(UTC).astimezone(LIMA_TZ).date() - timedelta(days=1)
            await session.execute(
                text(
                    "INSERT INTO billing.credit_wallets "
                    "(user_id, free_credits, free_credits_date, paid_credits) "
                    "VALUES (:u, 0, :d, 15)"
                ),
                {"u": user_id, "d": yesterday_lima},
            )
            await session.commit()

        r_w2 = await client.get("/api/v1/billing/wallet", headers=headers)
        assert r_w2.status_code == 200
        w2 = r_w2.json()
        assert w2["free_credits"] == 10
        assert w2["paid_credits"] == 15
        assert w2["total_credits"] == 25
        assert w2["searches_available"] == 5

        # Verify DB row was not mutated
        async with session_factory() as session:
            db_free = (
                await session.execute(
                    text("SELECT free_credits FROM billing.credit_wallets WHERE user_id = :u"),
                    {"u": user_id},
                )
            ).scalar_one()
            assert db_free == 0
        _ = date
