from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.modules.iam.domain.model.aggregates.user import User
from src.modules.iam.domain.model.entities.refresh_token import RefreshToken
from src.modules.iam.domain.model.events.user_deleted import UserDeleted
from src.modules.iam.domain.model.events.user_verified import UserVerified
from src.modules.iam.domain.model.value_objects.email import Email
from src.modules.iam.domain.model.value_objects.full_name import FullName
from src.modules.iam.domain.model.value_objects.password_hash import PasswordHash
from src.modules.iam.domain.model.value_objects.plain_password import PlainPassword
from src.shared.domain.domain_error import DomainError


def test_iam_value_objects_validation() -> None:
    email = Email("  Ana.Torres@Mail.COM ")
    assert email.value == "ana.torres@mail.com"

    with pytest.raises(DomainError):
        Email("invalid-email")

    pw = PlainPassword("Viajar2026")
    assert pw.value == "Viajar2026"

    for invalid_pw in ("Corto1", "sololetraslargas", "123456789"):
        with pytest.raises(DomainError):
            PlainPassword(invalid_pw)

    name = FullName("  Ana Torres  ")
    assert name.value == "Ana Torres"
    with pytest.raises(DomainError):
        FullName("   ")


def test_user_aggregate_lifecycle_events_and_google_linking() -> None:
    now = datetime.now(UTC)
    user = User.register_local(
        email=Email("ana@mail.com"),
        full_name=FullName("Ana Torres"),
        password_hash=PasswordHash("$2b$12$abcdefghijklmnopqrstuv"),
        terms_version="2026-10",
        now=now,
    )
    assert user.email_verified is False
    assert user.can_login_with_password() is False
    assert user.pull_events() == []

    # Linking Google to an UNVERIFIED local user clears password_hash and verifies email
    user.link_google("google-sub-123", now=now)
    assert user.password_hash is None
    assert user.google_sub == "google-sub-123"
    assert user.email_verified is True
    events = user.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], UserVerified)

    # Idempotent verify_email
    user.verify_email(now)
    assert user.pull_events() == []

    # Account deletion anonymizes fields and emits UserDeleted
    uid = user.id.value
    user.delete(now)
    assert user.email.value == f"deleted-{uid}@navby.invalid"
    assert user.full_name.value == "Usuario eliminado"
    assert user.password_hash is None
    assert user.google_sub is None
    assert user.deleted_at == now
    del_events = user.pull_events()
    assert len(del_events) == 1
    assert isinstance(del_events[0], UserDeleted)


def test_refresh_token_rotation_and_revocation() -> None:
    now = datetime.now(UTC)
    rt = RefreshToken(
        id=uuid4(),
        user_id=uuid4(),
        token_hash="a" * 64,
        expires_at=now + timedelta(days=7),
        created_at=now,
    )
    assert rt.is_active(now) is True
    rt.rotate("b" * 64, now)
    assert rt.is_active(now) is False
    assert rt.replaced_by_hash == "b" * 64
    assert rt.revoked_at == now
