import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from src.main import build_outbox_relay, create_app
from src.modules.iam.application.acl.ports.email_sender import EmailSender
from src.modules.iam.interfaces.rest.router import get_email_sender
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


@pytest.fixture
async def clean_sprint5_state() -> None:
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
    client: AsyncClient, sender: SilentEmailSender, email: str = "itin@mail.com"
) -> tuple[UUID, str]:
    r_reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Viajar2026",
            "full_name": "Itin User",
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


async def test_ts29_ts30_ts31_ts32_itineraries_crud_idempotency_and_concurrent_limit(
    clean_sprint5_state: None,
) -> None:
    app = create_app()
    sender = SilentEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    transport = ASGITransport(app=app)

    dep_date = (datetime.now(UTC).astimezone(LIMA_TZ).date() + timedelta(days=10)).isoformat()
    ret_date = (datetime.now(UTC).astimezone(LIMA_TZ).date() + timedelta(days=20)).isoformat()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id, token = await _register_and_verify(client, sender, "itin1@mail.com")
        _, other_token = await _register_and_verify(client, sender, "itin2@mail.com")
        headers = {"Authorization": f"Bearer {token}"}
        other_headers = {"Authorization": f"Bearer {other_token}"}

        r_search = await client.post(
            "/api/v1/quotes/search",
            headers=headers,
            json={
                "trip_type": "ROUND_TRIP",
                "origins": ["LIM"],
                "destinations": ["MIA"],
                "departure_date": dep_date,
                "return_date": ret_date,
                "passengers": {"adults": 1, "children": 0, "infants": 0},
                "cabin": "ECONOMY",
                "currency": "USD",
            },
        )
        assert r_search.status_code == 200
        search_data = r_search.json()
        search_id = search_data["search_id"]
        offer_1 = search_data["podium"][0]["offer_id"]
        offer_2 = search_data["podium"][1]["offer_id"]
        offer_3 = search_data["podium"][2]["offer_id"]

        # TS-29 Invalid search or offer -> 404 SEARCH_NOT_FOUND / OFFER_NOT_FOUND
        r_bad_search = await client.post(
            "/api/v1/itineraries",
            headers=headers,
            json={"search_id": "srch_01J9Z000000000000000000000", "offer_id": offer_1},
        )
        assert r_bad_search.status_code == 404
        assert r_bad_search.json()["code"] == "SEARCH_NOT_FOUND"

        r_bad_offer = await client.post(
            "/api/v1/itineraries",
            headers=headers,
            json={"search_id": search_id, "offer_id": "0000000000000000"},
        )
        assert r_bad_offer.status_code == 404
        assert r_bad_offer.json()["code"] == "OFFER_NOT_FOUND"

        # TS-29 Save new itinerary -> 201
        r_save = await client.post(
            "/api/v1/itineraries",
            headers=headers,
            json={"search_id": search_id, "offer_id": offer_1},
        )
        assert r_save.status_code == 201
        itin_body = r_save.json()
        itin_id = itin_body["id"]
        assert itin_body["origin"] == "LIM"
        assert itin_body["destination"] == "MIA"
        assert "quoted_at" in itin_body["offer"]
        assert "created_at" in itin_body
        assert itin_body["price_disclaimer"].startswith("Precio del ")

        # TS-29 Idempotent save of same offer_id -> 200 with existing itinerary
        r_save_dup = await client.post(
            "/api/v1/itineraries",
            headers=headers,
            json={"search_id": search_id, "offer_id": offer_1, "name": "Ignored New Name"},
        )
        assert r_save_dup.status_code == 200
        assert r_save_dup.json()["id"] == itin_id

        # TS-30 GET /itineraries list and isolation
        r_list = await client.get("/api/v1/itineraries", headers=headers)
        assert r_list.status_code == 200
        assert r_list.json()["total"] == 1
        assert r_list.json()["items"][0]["id"] == itin_id

        r_list_other = await client.get("/api/v1/itineraries", headers=other_headers)
        assert r_list_other.status_code == 200
        assert r_list_other.json()["total"] == 0

        # TS-31 GET /itineraries/{id} own vs foreign
        r_detail = await client.get(f"/api/v1/itineraries/{itin_id}", headers=headers)
        assert r_detail.status_code == 200
        assert r_detail.json()["id"] == itin_id
        assert "Precio del " in r_detail.json()["price_disclaimer"]

        r_detail_other = await client.get(f"/api/v1/itineraries/{itin_id}", headers=other_headers)
        assert r_detail_other.status_code == 404
        assert r_detail_other.json()["code"] == "ITINERARY_NOT_FOUND"

        # TS-32 DELETE /itineraries/{id} foreign -> 404; own -> 204
        r_del_other = await client.delete(f"/api/v1/itineraries/{itin_id}", headers=other_headers)
        assert r_del_other.status_code == 404

        r_del_own = await client.delete(f"/api/v1/itineraries/{itin_id}", headers=headers)
        assert r_del_own.status_code == 204

        r_after_del = await client.get(f"/api/v1/itineraries/{itin_id}", headers=headers)
        assert r_after_del.status_code == 404

        # TS-29 Concurrent limit: seed 49 itineraries, then send 2 distinct saves simultaneously
        session_factory = get_session_factory()
        now = datetime.now(UTC)
        async with session_factory() as session:
            for idx in range(49):
                await session.execute(
                    text(
                        "INSERT INTO itineraries.saved_itineraries "
                        "(id, user_id, offer_id, name, trip_type, origin, "
                        "destination, departure_date, offer_snapshot, created_at) "
                        "VALUES (:id, :u, :off, :name, 'ONE_WAY', 'LIM', "
                        "'MIA', CURRENT_DATE, '{}'::jsonb, :ts)"
                    ),
                    {
                        "id": uuid4(),
                        "u": user_id,
                        "off": f"seed_off_{idx:02d}",
                        "name": f"Trip {idx}",
                        "ts": now,
                    },
                )
            await session.commit()

        res_c1, res_c2 = await asyncio.gather(
            client.post(
                "/api/v1/itineraries",
                headers=headers,
                json={"search_id": search_id, "offer_id": offer_2},
            ),
            client.post(
                "/api/v1/itineraries",
                headers=headers,
                json={"search_id": search_id, "offer_id": offer_3},
            ),
        )
        statuses = sorted([res_c1.status_code, res_c2.status_code])
        assert statuses == [201, 409]
        failed_resp = res_c1 if res_c1.status_code == 409 else res_c2
        assert failed_resp.json()["code"] == "ITINERARY_LIMIT_REACHED"
