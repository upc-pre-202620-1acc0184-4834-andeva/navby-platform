import asyncio
import hashlib
import hmac
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from src.main import build_outbox_relay, create_app
from src.modules.billing.application.acl.ports.payment_gateway import PaymentGateway
from src.modules.billing.application.commands.expire_pending_orders import (
    ExpirePendingOrdersHandler,
)
from src.modules.billing.domain.model.aggregates.credit_order import CreditOrder
from src.modules.billing.domain.model.value_objects.payment_info import PaymentInfo
from src.modules.billing.infrastructure.adapters.mercadopago_payment_gateway import (
    verify_mp_webhook_signature,
)
from src.modules.billing.interfaces.rest.router import get_payment_gateway
from src.modules.iam.application.acl.ports.email_sender import EmailSender
from src.modules.iam.application.commands.purge_expired_tokens import (
    PurgeExpiredTokensHandler,
)
from src.modules.iam.interfaces.rest.router import get_email_sender
from src.shared.infrastructure.database import get_session_factory
from src.shared.infrastructure.redis_client import get_redis_client
from src.shared.infrastructure.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork


class SilentEmailSender(EmailSender):
    def __init__(self) -> None:
        self.codes: list[str] = []

    async def send_verification_code(self, email: str, code: str) -> None:
        self.codes.append(code)

    async def send_password_reset(self, email: str, link: str) -> None:
        pass


class FakePaymentGateway(PaymentGateway):
    def __init__(self, secret: str = "test_webhook_secret") -> None:
        self.secret = secret
        self.payments: dict[str, PaymentInfo] = {}
        self.created_orders: list[CreditOrder] = []
        self.get_payment_calls: int = 0

    async def create_preference(self, order: CreditOrder) -> tuple[str, str]:
        self.created_orders.append(order)
        pref_id = f"pref_{order.id}"
        url = f"https://www.mercadopago.com.pe/checkout/v1/redirect?pref_id={pref_id}"
        return pref_id, url

    async def get_payment(self, payment_id: str) -> PaymentInfo | None:
        self.get_payment_calls += 1
        return self.payments.get(payment_id)

    def verify_signature(self, x_signature: str, x_request_id: str, data_id: str) -> bool:
        return verify_mp_webhook_signature(
            x_signature=x_signature,
            x_request_id=x_request_id,
            data_id=data_id,
            secret=self.secret,
        )


def _sign_webhook(
    data_id: str, secret: str = "test_webhook_secret", ts_offset: int = 0
) -> dict[str, str]:
    ts = int(datetime.now(UTC).timestamp()) + ts_offset
    req_id = f"req-{uuid4()}"
    manifest = f"id:{data_id};request-id:{req_id};ts:{ts};"
    sig = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return {
        "x-signature": f"ts={ts},v1={sig}",
        "x-request-id": req_id,
    }


@pytest.fixture
async def clean_sprint4_state() -> None:
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
    client: AsyncClient, sender: SilentEmailSender, email: str = "buyer@mail.com"
) -> tuple[UUID, str]:
    r_reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Viajar2026",
            "full_name": "Buyer",
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


async def test_ts18_ts19_packages_and_transactions_pagination(
    clean_sprint4_state: None,
) -> None:
    app = create_app()
    sender = SilentEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # TS-19 Public packages endpoint without JWT
        r_pkg = await client.get("/api/v1/billing/packages")
        assert r_pkg.status_code == 200
        pkg_data = r_pkg.json()
        assert pkg_data["currency"] == "PEN"
        assert len(pkg_data["packages"]) == 3
        codes = [p["code"] for p in pkg_data["packages"]]
        assert codes == ["pack_50", "pack_100", "pack_250"]
        assert pkg_data["packages"][1]["price"] == "16.90"
        assert pkg_data["packages"][1]["usd_reference"] == "4.49"

        # TS-18 Transactions pagination & isolation
        user_1, token_1 = await _register_and_verify(client, sender, "u1@mail.com")
        user_2, _ = await _register_and_verify(client, sender, "u2@mail.com")
        headers_1 = {"Authorization": f"Bearer {token_1}"}

        session_factory = get_session_factory()
        base_time = datetime.now(UTC) - timedelta(hours=2)
        async with session_factory() as session:
            for i in range(25):
                await session.execute(
                    text(
                        "INSERT INTO billing.credit_transactions "
                        "(id, user_id, type, free_delta, paid_delta, reference_id, created_at) "
                        "VALUES (:id, :u, 'SEARCH_DEBIT', -5, 0, :ref, :ts)"
                    ),
                    {
                        "id": uuid4(),
                        "u": user_1,
                        "ref": f"srch_{i:02d}",
                        "ts": base_time + timedelta(minutes=i),
                    },
                )
            await session.execute(
                text(
                    "INSERT INTO billing.credit_transactions "
                    "(id, user_id, type, free_delta, paid_delta, reference_id, created_at) "
                    "VALUES (:id, :u, 'PURCHASE', 0, 100, 'ord_other', :ts)"
                ),
                {"id": uuid4(), "u": user_2, "ts": datetime.now(UTC)},
            )
            await session.commit()

        r_tx_p2 = await client.get(
            "/api/v1/billing/transactions?page=2&page_size=20",
            headers=headers_1,
        )
        assert r_tx_p2.status_code == 200
        tx_body = r_tx_p2.json()
        assert tx_body["total"] == 25
        assert tx_body["page"] == 2
        assert tx_body["page_size"] == 20
        assert len(tx_body["items"]) == 5
        # Descending order: srch_04, srch_03, srch_02, srch_01, srch_00
        assert [it["reference_id"] for it in tx_body["items"]] == [
            "srch_04",
            "srch_03",
            "srch_02",
            "srch_01",
            "srch_00",
        ]

        # page_size > 50 -> 422 VALIDATION_ERROR
        r_tx_bad = await client.get(
            "/api/v1/billing/transactions?page=1&page_size=51",
            headers=headers_1,
        )
        assert r_tx_bad.status_code == 422
        assert r_tx_bad.json()["code"] == "VALIDATION_ERROR"


async def test_ts20_ts21_ts22_orders_and_mercadopago_webhook(
    clean_sprint4_state: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app()
    sender = SilentEmailSender()
    gateway = FakePaymentGateway()
    app.dependency_overrides[get_email_sender] = lambda: sender
    app.dependency_overrides[get_payment_gateway] = lambda: gateway
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id, token = await _register_and_verify(client, sender, "mp@mail.com")
        _, other_token = await _register_and_verify(client, sender, "other@mail.com")
        headers = {"Authorization": f"Bearer {token}"}
        other_headers = {"Authorization": f"Bearer {other_token}"}

        # TS-20 Unknown package -> 404 PACKAGE_NOT_FOUND
        r_no_pkg = await client.post(
            "/api/v1/billing/orders",
            headers=headers,
            json={"package_code": "pack_999"},
        )
        assert r_no_pkg.status_code == 404
        assert r_no_pkg.json()["code"] == "PACKAGE_NOT_FOUND"

        # TS-20 Valid order creation -> 201 PENDING
        r_ord = await client.post(
            "/api/v1/billing/orders",
            headers=headers,
            json={"package_code": "pack_100"},
        )
        assert r_ord.status_code == 201
        ord_data = r_ord.json()
        order_id = ord_data["order_id"]
        assert ord_data["amount"] == "16.90"
        assert ord_data["currency"] == "PEN"
        assert ord_data["status"] == "PENDING"
        assert ord_data["checkout_url"].startswith("https://www.mercadopago.com.pe/")

        # TS-21 GET own order -> 200; foreign order -> 404 ORDER_NOT_FOUND
        r_get_own = await client.get(f"/api/v1/billing/orders/{order_id}", headers=headers)
        assert r_get_own.status_code == 200
        assert r_get_own.json()["status"] == "PENDING"

        r_get_foreign = await client.get(
            f"/api/v1/billing/orders/{order_id}", headers=other_headers
        )
        assert r_get_foreign.status_code == 404
        assert r_get_foreign.json()["code"] == "ORDER_NOT_FOUND"

        # TS-22 Webhook non-payment type -> 200 without calling get_payment
        r_non_pay = await client.post(
            "/api/v1/billing/webhooks/mercadopago",
            json={"type": "merchant_order", "data": {"id": "123"}},
        )
        assert r_non_pay.status_code == 200
        assert gateway.get_payment_calls == 0

        # TS-22 Invalid signature or old ts -> 401 INVALID_WEBHOOK_SIGNATURE
        r_bad_sig = await client.post(
            "/api/v1/billing/webhooks/mercadopago",
            headers=_sign_webhook("pay_1", ts_offset=-400),
            json={"type": "payment", "data": {"id": "pay_1"}},
        )
        assert r_bad_sig.status_code == 401
        assert r_bad_sig.json()["code"] == "INVALID_WEBHOOK_SIGNATURE"

        # TS-22 Payment mismatch (S/ 1.00 for S/ 16.90 order) -> 200, stays PENDING, logs CRITICAL
        gateway.payments["pay_mismatch"] = PaymentInfo(
            payment_id="pay_mismatch",
            status="approved",
            external_reference=order_id,
            amount=Decimal("1.00"),
            currency="PEN",
        )
        caplog.set_level(logging.CRITICAL)
        r_mis = await client.post(
            "/api/v1/billing/webhooks/mercadopago",
            headers=_sign_webhook("pay_mismatch"),
            json={"type": "payment", "data": {"id": "pay_mismatch"}},
        )
        assert r_mis.status_code == 200
        assert any("PAYMENT_MISMATCH" in rec.message for rec in caplog.records)

        r_after_mis = await client.get(f"/api/v1/billing/orders/{order_id}", headers=headers)
        assert r_after_mis.json()["status"] == "PENDING"

        # TS-22 Approved payment notified 3 times in parallel -> credits added once!
        gateway.payments["pay_good"] = PaymentInfo(
            payment_id="pay_good",
            status="approved",
            external_reference=order_id,
            amount=Decimal("16.90"),
            currency="PEN",
        )
        wh_headers = _sign_webhook("pay_good")
        wh_body = {"type": "payment", "data": {"id": "pay_good"}}
        res_1, res_2, res_3 = await asyncio.gather(
            client.post("/api/v1/billing/webhooks/mercadopago", headers=wh_headers, json=wh_body),
            client.post("/api/v1/billing/webhooks/mercadopago", headers=wh_headers, json=wh_body),
            client.post("/api/v1/billing/webhooks/mercadopago", headers=wh_headers, json=wh_body),
        )
        assert [res_1.status_code, res_2.status_code, res_3.status_code] == [200, 200, 200]

        r_wallet = await client.get("/api/v1/billing/wallet", headers=headers)
        assert r_wallet.json()["paid_credits"] == 100

        # TS-22 Reversal (refunded) -> order REVERSED, subtracts up to 100 paid_credits
        session_factory = get_session_factory()
        async with session_factory() as session:
            # Simulate user spent 60 of the 100 paid credits (leaving 40)
            await session.execute(
                text("UPDATE billing.credit_wallets SET paid_credits = 40 WHERE user_id = :u"),
                {"u": user_id},
            )
            await session.commit()

        gateway.payments["pay_good"] = PaymentInfo(
            payment_id="pay_good",
            status="refunded",
            external_reference=order_id,
            amount=Decimal("16.90"),
            currency="PEN",
        )
        r_rev = await client.post(
            "/api/v1/billing/webhooks/mercadopago",
            headers=_sign_webhook("pay_good"),
            json={"type": "payment", "data": {"id": "pay_good"}},
        )
        assert r_rev.status_code == 200

        r_ord_rev = await client.get(f"/api/v1/billing/orders/{order_id}", headers=headers)
        assert r_ord_rev.json()["status"] == "REVERSED"

        r_wallet_after = await client.get("/api/v1/billing/wallet", headers=headers)
        assert r_wallet_after.json()["paid_credits"] == 0


async def test_ts35_periodic_tasks_expire_orders_and_purge_tokens(
    clean_sprint4_state: None,
) -> None:
    session_factory = get_session_factory()
    now = datetime.now(UTC)
    expired_order_id = uuid4()
    active_order_id = uuid4()
    user_id = uuid4()
    tok_31d = uuid4()
    tok_5d = uuid4()

    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO iam.users "
                "(id, email, full_name, google_sub, email_verified, "
                "terms_version, terms_accepted_at, created_at, updated_at) "
                "VALUES (:u, 'periodic@mail.com', 'Periodic', 'gsub_p', true, "
                "'2026-10', :now, :now, :now)"
            ),
            {"u": user_id, "now": now},
        )
        await session.execute(
            text(
                "INSERT INTO billing.credit_orders "
                "(id, user_id, package_code, credits, amount, currency, "
                "status, expires_at, mp_preference_id, created_at, updated_at) "
                "VALUES "
                "(:o1, :u, 'pack_50', 50, 9.90, 'PEN', "
                "'PENDING', :past, 'p1', :now, :now), "
                "(:o2, :u, 'pack_50', 50, 9.90, 'PEN', "
                "'PENDING', :future, 'p2', :now, :now)"
            ),
            {
                "o1": expired_order_id,
                "o2": active_order_id,
                "u": user_id,
                "past": now - timedelta(hours=1),
                "future": now + timedelta(hours=10),
                "now": now,
            },
        )
        await session.execute(
            text(
                "INSERT INTO iam.refresh_tokens (id, user_id, token_hash, expires_at, created_at) "
                "VALUES "
                "(:t1, :u, 'hash_31d', :exp31, :now), "
                "(:t2, :u, 'hash_5d', :exp5, :now)"
            ),
            {
                "t1": tok_31d,
                "t2": tok_5d,
                "u": user_id,
                "exp31": now - timedelta(days=31),
                "exp5": now - timedelta(days=5),
                "now": now,
            },
        )
        await session.commit()

    from src.modules.billing.infrastructure.persistence.sqlalchemy_credit_order_repository import (
        SqlAlchemyCreditOrderRepository,
    )
    from src.modules.iam.infrastructure.persistence.sqlalchemy_refresh_token_repository import (
        SqlAlchemyRefreshTokenRepository,
    )

    uow_exp = SqlAlchemyUnitOfWork(session_factory)
    exp_handler = ExpirePendingOrdersHandler(
        uow=uow_exp, order_repo=SqlAlchemyCreditOrderRepository(uow_exp)
    )
    expired_count = await exp_handler.handle()
    assert expired_count == 1

    uow_purge = SqlAlchemyUnitOfWork(session_factory)
    purge_handler = PurgeExpiredTokensHandler(
        uow=uow_purge, refresh_repo=SqlAlchemyRefreshTokenRepository(uow_purge)
    )
    purged_count = await purge_handler.handle()
    assert purged_count == 1

    async with session_factory() as session:
        st_1 = (
            await session.execute(
                text("SELECT status FROM billing.credit_orders WHERE id = :id"),
                {"id": expired_order_id},
            )
        ).scalar_one()
        st_2 = (
            await session.execute(
                text("SELECT status FROM billing.credit_orders WHERE id = :id"),
                {"id": active_order_id},
            )
        ).scalar_one()
        assert st_1 == "EXPIRED"
        assert st_2 == "PENDING"

        remaining_tokens = [
            r[0] for r in (await session.execute(text("SELECT id FROM iam.refresh_tokens"))).all()
        ]
        assert remaining_tokens == [tok_5d]
