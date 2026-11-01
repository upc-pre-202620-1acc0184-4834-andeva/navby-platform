import hashlib
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from src.main import create_app
from src.modules.iam.application.acl.ports.email_sender import EmailSender
from src.modules.iam.application.acl.ports.google_identity_verifier import (
    GoogleIdentity,
    GoogleIdentityVerifier,
)
from src.modules.iam.interfaces.rest.router import (
    get_email_sender,
    get_google_verifier,
)
from src.shared.infrastructure.database import get_session_factory
from src.shared.infrastructure.redis_client import get_redis_client
from src.shared.infrastructure.settings import Settings, get_settings


class RecordingEmailSender(EmailSender):
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.verification_codes: list[tuple[str, str]] = []
        self.reset_links: list[tuple[str, str]] = []

    async def send_verification_code(self, email: str, code: str) -> None:
        if self.should_fail:
            raise RuntimeError("Resend API error")
        self.verification_codes.append((email, code))

    async def send_password_reset(self, email: str, link: str) -> None:
        if self.should_fail:
            raise RuntimeError("Resend API error")
        self.reset_links.append((email, link))


class FakeGoogleVerifier(GoogleIdentityVerifier):
    def __init__(self, identities: dict[str, GoogleIdentity]) -> None:
        self.identities = identities

    async def verify(self, id_token: str) -> GoogleIdentity | None:
        return self.identities.get(id_token)


@pytest.fixture
async def clean_iam_state() -> None:
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


async def test_ts01_register_valid_validations_and_email_failure(
    clean_iam_state: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app()
    sender = RecordingEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "Ana@Mail.com",
                "password": "Viajar2026",
                "full_name": "Ana Torres",
                "accept_terms": True,
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["email"] == "ana@mail.com"
        assert data["email_verified"] is False
        user_id = UUID(data["user_id"])

        assert len(sender.verification_codes) == 1
        sent_email, sent_code = sender.verification_codes[0]
        assert sent_email == "ana@mail.com"
        assert len(sent_code) == 6 and sent_code.isdigit()

        redis = get_redis_client()
        otp_key = f"navby:iam:verify:{user_id}"
        stored_hash = await redis.hget(otp_key, "code_hash")
        ttl = await redis.ttl(otp_key)
        await redis.aclose()
        assert stored_hash == hashlib.sha256(sent_code.encode()).hexdigest()
        assert 0 < ttl <= 600

        session_factory = get_session_factory()
        async with session_factory() as session:
            u_row = (
                await session.execute(
                    text(
                        "SELECT password_hash, terms_version, terms_accepted_at "
                        "FROM iam.users WHERE id = :id"
                    ),
                    {"id": user_id},
                )
            ).first()
            assert u_row is not None
            assert str(u_row[0]).startswith("$2b$")
            assert u_row[1] == get_settings().terms_version
            assert u_row[2] is not None

            outbox_count = (
                await session.execute(text("SELECT count(*) FROM shared.outbox_events"))
            ).scalar_one()
            assert outbox_count == 0

        # Duplicate email (case-insensitive) -> 409 EMAIL_ALREADY_REGISTERED
        r_dup = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "ANA@mail.com",
                "password": "Viajar2026",
                "full_name": "Ana",
                "accept_terms": True,
            },
        )
        assert r_dup.status_code == 409
        assert r_dup.json()["code"] == "EMAIL_ALREADY_REGISTERED"

        # Terms false -> 422 TERMS_NOT_ACCEPTED
        r_terms = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "otra@mail.com",
                "password": "Viajar2026",
                "full_name": "Otra",
                "accept_terms": False,
            },
        )
        assert r_terms.status_code == 422
        assert r_terms.json()["code"] == "TERMS_NOT_ACCEPTED"

        # Disposable email -> 422 DISPOSABLE_EMAIL
        r_disp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "temp@mailinator.com",
                "password": "Viajar2026",
                "full_name": "Temp",
                "accept_terms": True,
            },
        )
        assert r_disp.status_code == 422
        assert r_disp.json()["code"] == "DISPOSABLE_EMAIL"

        # Weak password -> 422 VALIDATION_ERROR
        r_weak = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "weak@mail.com",
                "password": "corto1",
                "full_name": "Weak",
                "accept_terms": True,
            },
        )
        assert r_weak.status_code == 422
        assert r_weak.json()["code"] == "VALIDATION_ERROR"

        # 6th request in the same minute hits register rate limit (5 / min) -> 429 RATE_LIMITED
        r_rl = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "ratelimited@mail.com",
                "password": "Viajar2026",
                "full_name": "Rate Limited",
                "accept_terms": True,
            },
        )
        assert r_rl.status_code == 429
        assert r_rl.json()["code"] == "RATE_LIMITED"

        # Clear rate-limit keys to test email provider failure scenario
        redis_rl = get_redis_client()
        rl_keys = await redis_rl.keys("navby:ratelimit:*")
        if rl_keys:
            await redis_rl.delete(*rl_keys)
        await redis_rl.aclose()

        # Email provider failure still returns 201 and logs ERROR
        sender.should_fail = True
        caplog.set_level(logging.ERROR)
        r_fail_mail = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "resilient@mail.com",
                "password": "Viajar2026",
                "full_name": "Resilient",
                "accept_terms": True,
            },
        )
        assert r_fail_mail.status_code == 201
        assert any(rec.levelname == "ERROR" for rec in caplog.records)


async def test_ts02_ts03_verify_email_and_resend(clean_iam_state: None) -> None:
    app = create_app()
    sender = RecordingEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_reg = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "verify@mail.com",
                "password": "Viajar2026",
                "full_name": "Verify User",
                "accept_terms": True,
            },
        )
        user_id = r_reg.json()["user_id"]
        first_code = sender.verification_codes[-1][1]

        # Non-existent email -> 400 INVALID_OTP
        r_non = await client.post(
            "/api/v1/auth/verify-email",
            json={"email": "nobody@mail.com", "code": "123456"},
        )
        assert r_non.status_code == 400
        assert r_non.json()["code"] == "INVALID_OTP"

        # 4 wrong attempts -> 400 INVALID_OTP; 5th wrong attempt -> 429 OTP_ATTEMPTS_EXCEEDED
        for _ in range(4):
            r_bad = await client.post(
                "/api/v1/auth/verify-email",
                json={"email": "verify@mail.com", "code": "000000"},
            )
            assert r_bad.status_code == 400
            assert r_bad.json()["code"] == "INVALID_OTP"

        r_5th = await client.post(
            "/api/v1/auth/verify-email",
            json={"email": "verify@mail.com", "code": "000000"},
        )
        assert r_5th.status_code == 429
        assert r_5th.json()["code"] == "OTP_ATTEMPTS_EXCEEDED"

        # Resend OTP (TS-03)
        r_resend = await client.post(
            "/api/v1/auth/verify-email/resend",
            json={"email": "verify@mail.com"},
        )
        assert r_resend.status_code == 202
        new_code = sender.verification_codes[-1][1]
        assert len(sender.verification_codes) == 2
        _ = first_code

        # Resend within 60s -> 202 without sending email
        r_resend_again = await client.post(
            "/api/v1/auth/verify-email/resend",
            json={"email": "verify@mail.com"},
        )
        assert r_resend_again.status_code == 202
        assert len(sender.verification_codes) == 2

        # Correct OTP -> 200 Session + navby_refresh cookie + outbox iam.user_verified
        r_ok = await client.post(
            "/api/v1/auth/verify-email",
            json={"email": "verify@mail.com", "code": new_code},
        )
        assert r_ok.status_code == 200
        body = r_ok.json()
        assert body["access_token"]
        assert body["user"]["email_verified"] is True
        assert "navby_refresh" in r_ok.cookies

        redis = get_redis_client()
        assert await redis.exists(f"navby:iam:verify:{user_id}") == 0
        await redis.aclose()

        session_factory = get_session_factory()
        async with session_factory() as session:
            evt_row = (
                await session.execute(text("SELECT event_type, payload FROM shared.outbox_events"))
            ).first()
            assert evt_row is not None
            assert evt_row[0] == "iam.user_verified"
            assert evt_row[1]["user_id"] == user_id

        # Already verified -> 400 INVALID_OTP
        r_already = await client.post(
            "/api/v1/auth/verify-email",
            json={"email": "verify@mail.com", "code": new_code},
        )
        assert r_already.status_code == 400
        assert r_already.json()["code"] == "INVALID_OTP"


async def test_ts04_ts05_ts06_ts07_login_google_refresh_logout(
    clean_iam_state: None,
) -> None:
    app = create_app()
    sender = RecordingEmailSender()
    google_verifier = FakeGoogleVerifier(
        {
            "valid-new-token": GoogleIdentity(
                sub="gsub-new",
                email="gnew@mail.com",
                email_verified=True,
                name="Google New",
            ),
            "valid-link-token": GoogleIdentity(
                sub="gsub-link",
                email="unverified@mail.com",
                email_verified=True,
                name="Unverified Link",
            ),
        }
    )
    app.dependency_overrides[get_email_sender] = lambda: sender
    app.dependency_overrides[get_google_verifier] = lambda: google_verifier
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register unverified user
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "unverified@mail.com",
                "password": "Viajar2026",
                "full_name": "Unverified",
                "accept_terms": True,
            },
        )
        # Login before verification -> 403 EMAIL_NOT_VERIFIED
        r_unv = await client.post(
            "/api/v1/auth/login",
            json={"email": "unverified@mail.com", "password": "Viajar2026"},
        )
        assert r_unv.status_code == 403
        assert r_unv.json()["code"] == "EMAIL_NOT_VERIFIED"

        # Wrong password or non-existent user -> 401 INVALID_CREDENTIALS
        r_bad_pw = await client.post(
            "/api/v1/auth/login",
            json={"email": "unverified@mail.com", "password": "WrongPassword1"},
        )
        assert r_bad_pw.status_code == 401
        assert r_bad_pw.json()["code"] == "INVALID_CREDENTIALS"

        r_no_user = await client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@mail.com", "password": "Viajar2026"},
        )
        assert r_no_user.status_code == 401
        assert r_no_user.json()["code"] == "INVALID_CREDENTIALS"

        # TS-05 Google linking on unverified account -> clears password_hash & verifies
        r_glink = await client.post(
            "/api/v1/auth/google",
            json={"id_token": "valid-link-token"},
        )
        assert r_glink.status_code == 200
        assert r_glink.json()["user"]["email_verified"] is True

        # Password login on Google-only account -> 401 INVALID_CREDENTIALS
        r_pw_after_link = await client.post(
            "/api/v1/auth/login",
            json={"email": "unverified@mail.com", "password": "Viajar2026"},
        )
        assert r_pw_after_link.status_code == 401

        # TS-05 New Google account without accept_terms -> 422 TERMS_NOT_ACCEPTED
        r_g_noterms = await client.post(
            "/api/v1/auth/google",
            json={"id_token": "valid-new-token", "accept_terms": False},
        )
        assert r_g_noterms.status_code == 422
        assert r_g_noterms.json()["code"] == "TERMS_NOT_ACCEPTED"

        # TS-05 New Google account with accept_terms=True -> 200 Session
        r_g_ok = await client.post(
            "/api/v1/auth/google",
            json={"id_token": "valid-new-token", "accept_terms": True},
        )
        assert r_g_ok.status_code == 200

        # TS-05 Invalid Google token -> 401 INVALID_GOOGLE_TOKEN
        r_g_inv = await client.post(
            "/api/v1/auth/google",
            json={"id_token": "invalid-token", "accept_terms": True},
        )
        assert r_g_inv.status_code == 401
        assert r_g_inv.json()["code"] == "INVALID_GOOGLE_TOKEN"

        # Register & verify a password user for TS-04, TS-06, TS-07
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "local@mail.com",
                "password": "Viajar2026",
                "full_name": "Local User",
                "accept_terms": True,
            },
        )
        otp = sender.verification_codes[-1][1]
        await client.post(
            "/api/v1/auth/verify-email",
            json={"email": "local@mail.com", "code": otp},
        )

        r_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "local@mail.com", "password": "Viajar2026"},
        )
        assert r_login.status_code == 200
        cookie_token_1 = r_login.cookies.get("navby_refresh")
        assert cookie_token_1 is not None

        # TS-06 Refresh rotation
        client.cookies.set("navby_refresh", cookie_token_1)
        r_ref1 = await client.post("/api/v1/auth/refresh")
        assert r_ref1.status_code == 200
        cookie_token_2 = r_ref1.cookies.get("navby_refresh")
        assert cookie_token_2 is not None
        assert cookie_token_2 != cookie_token_1

        # TS-06 Tab race (< 30 s since rotation): presenting cookie_token_1 again succeeds!
        client.cookies.set("navby_refresh", cookie_token_1)
        r_race = await client.post("/api/v1/auth/refresh")
        assert r_race.status_code == 200

        # TS-06 Suspicious reuse (> 30 s since rotation): backdate revoked_at to 2 minutes ago
        hash_1 = hashlib.sha256(cookie_token_1.encode()).hexdigest()
        session_factory = get_session_factory()
        async with session_factory() as session:
            await session.execute(
                text("UPDATE iam.refresh_tokens SET revoked_at = :old WHERE token_hash = :h"),
                {"old": datetime.now(UTC) - timedelta(minutes=2), "h": hash_1},
            )
            await session.commit()

        client.cookies.set("navby_refresh", cookie_token_1)
        r_reuse = await client.post("/api/v1/auth/refresh")
        assert r_reuse.status_code == 401
        assert r_reuse.json()["code"] == "INVALID_REFRESH_TOKEN"

        # All tokens for user were revoked, so cookie_token_2 is now also invalid
        client.cookies.set("navby_refresh", cookie_token_2)
        r_after_revoke = await client.post("/api/v1/auth/refresh")
        assert r_after_revoke.status_code == 401

        # TS-07 Logout idempotent
        r_logout = await client.post("/api/v1/auth/logout")
        assert r_logout.status_code == 204


async def test_ts08_ts09_ts10_ts11_forgot_reset_me_and_delete(
    clean_iam_state: None,
) -> None:
    app = create_app()
    sender = RecordingEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_env="local",
        jwt_secret=get_settings().jwt_secret,
        webapp_url="https://navby.andeva.tech/app",
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_reg = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "reset@mail.com",
                "password": "Viajar2026",
                "full_name": "Reset User",
                "accept_terms": True,
            },
        )
        user_id = UUID(r_reg.json()["user_id"])

        # TS-08 Forgot password for existing user
        r_forgot = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "reset@mail.com"},
        )
        assert r_forgot.status_code == 202
        assert len(sender.reset_links) == 1
        reset_link = sender.reset_links[0][1]
        assert reset_link.startswith("https://navby.andeva.tech/app/reset-password?token=")
        raw_token = reset_link.split("token=")[1]

        # Non-existent user -> 202 without sending email
        r_forgot_no = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "nobody@mail.com"},
        )
        assert r_forgot_no.status_code == 202
        assert len(sender.reset_links) == 1

        # TS-09 Weak password on reset -> 422 VALIDATION_ERROR and token stays valid
        r_reset_weak = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw_token, "new_password": "short"},
        )
        assert r_reset_weak.status_code == 422
        assert r_reset_weak.json()["code"] == "VALIDATION_ERROR"

        # TS-09 Valid reset -> 204, updates password and verifies email
        r_reset_ok = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw_token, "new_password": "NuevaPassword2026"},
        )
        assert r_reset_ok.status_code == 204

        # Reusing the token -> 400 INVALID_RESET_TOKEN
        r_reset_used = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw_token, "new_password": "NuevaPassword2026"},
        )
        assert r_reset_used.status_code == 400
        assert r_reset_used.json()["code"] == "INVALID_RESET_TOKEN"

        # Login with new password
        r_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "reset@mail.com", "password": "NuevaPassword2026"},
        )
        assert r_login.status_code == 200
        access_token = r_login.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {access_token}"}

        # TS-10 GET /users/me
        r_me = await client.get("/api/v1/users/me", headers=auth_headers)
        assert r_me.status_code == 200
        me_data = r_me.json()
        assert me_data["user_id"] == str(user_id)
        assert me_data["email"] == "reset@mail.com"
        assert me_data["full_name"] == "Reset User"
        assert me_data["email_verified"] is True
        assert me_data["has_password"] is True
        assert me_data["has_google"] is False
        assert "created_at" in me_data

        # TS-11 Wrong confirmation -> 422 VALIDATION_ERROR
        r_del_bad = await client.request(
            "DELETE",
            "/api/v1/users/me",
            headers=auth_headers,
            json={"confirmation": "BORRAR"},
        )
        assert r_del_bad.status_code == 422
        assert r_del_bad.json()["code"] == "VALIDATION_ERROR"

        # Seed wallet, credit_order, and saved_itinerary to verify TS-11 cross-context effects
        session_factory = get_session_factory()
        order_id = uuid4()
        async with session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO billing.credit_wallets "
                    "(user_id, free_credits, free_credits_date, paid_credits) "
                    "VALUES (:u, 10, CURRENT_DATE, 50) "
                    "ON CONFLICT (user_id) DO UPDATE SET "
                    "free_credits = 10, paid_credits = 50"
                ),
                {"u": user_id},
            )
            await session.execute(
                text(
                    "INSERT INTO billing.credit_orders "
                    "(id, user_id, package_code, credits, amount, currency, "
                    "status, expires_at, mp_preference_id) "
                    "VALUES (:id, :u, 'pack_50', 50, 9.90, 'PEN', "
                    "'APPROVED', now() + interval '1 day', 'pref_1')"
                ),
                {"id": order_id, "u": user_id},
            )
            await session.execute(
                text(
                    "INSERT INTO itineraries.saved_itineraries "
                    "(id, user_id, offer_id, name, trip_type, origin, "
                    "destination, departure_date, offer_snapshot) "
                    "VALUES (:id, :u, 'off_1', 'Trip', 'ONE_WAY', 'LIM', "
                    "'MIA', CURRENT_DATE, '{}'::jsonb)"
                ),
                {"id": uuid4(), "u": user_id},
            )
            await session.commit()

        # TS-11 DELETE /users/me with confirmation == "ELIMINAR"
        r_del_ok = await client.request(
            "DELETE",
            "/api/v1/users/me",
            headers=auth_headers,
            json={"confirmation": "ELIMINAR"},
        )
        assert r_del_ok.status_code == 204

        # Process outbox via app relay or new relay with registered handlers
        from src.main import build_outbox_relay

        relay = build_outbox_relay(session_factory)
        await relay.process_pending_batch()

        async with session_factory() as session:
            u_row = (
                await session.execute(
                    text(
                        "SELECT email, full_name, password_hash, google_sub, deleted_at "
                        "FROM iam.users WHERE id = :u"
                    ),
                    {"u": user_id},
                )
            ).first()
            assert u_row is not None
            assert u_row[0] == f"deleted-{user_id}@navby.invalid"
            assert u_row[1] == "Usuario eliminado"
            assert u_row[2] is None
            assert u_row[3] is None
            assert u_row[4] is not None

            w_row = (
                await session.execute(
                    text(
                        "SELECT free_credits, paid_credits "
                        "FROM billing.credit_wallets WHERE user_id = :u"
                    ),
                    {"u": user_id},
                )
            ).first()
            assert w_row == (0, 0)

            tx_row = (
                await session.execute(
                    text(
                        "SELECT type, free_delta, paid_delta FROM billing.credit_transactions "
                        "WHERE user_id = :u AND type = 'ACCOUNT_DELETION'"
                    ),
                    {"u": user_id},
                )
            ).first()
            assert tx_row == ("ACCOUNT_DELETION", -10, -50)

            itin_count = (
                await session.execute(
                    text("SELECT count(*) FROM itineraries.saved_itineraries WHERE user_id = :u"),
                    {"u": user_id},
                )
            ).scalar_one()
            assert itin_count == 0

            ord_count = (
                await session.execute(
                    text("SELECT count(*) FROM billing.credit_orders WHERE id = :id"),
                    {"id": order_id},
                )
            ).scalar_one()
            assert ord_count == 1
