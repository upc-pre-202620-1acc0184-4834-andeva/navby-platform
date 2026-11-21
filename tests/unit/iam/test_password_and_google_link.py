from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Self, cast
from uuid import UUID

import pytest

from src.modules.iam.application.commands.set_password import (
    SetPasswordCommand,
    SetPasswordHandler,
)
from src.modules.iam.application.commands.unlink_google import (
    UnlinkGoogleCommand,
    UnlinkGoogleHandler,
)
from src.modules.iam.domain.model.aggregates.user import User
from src.modules.iam.domain.model.entities.refresh_token import RefreshToken
from src.modules.iam.domain.model.value_objects.email import Email
from src.modules.iam.domain.model.value_objects.full_name import FullName
from src.modules.iam.domain.model.value_objects.password_hash import PasswordHash
from src.modules.iam.domain.model.value_objects.plain_password import PlainPassword
from src.modules.iam.infrastructure.adapters.bcrypt_password_hasher import (
    BcryptPasswordHasher,
)
from src.shared.domain.domain_error import DomainError

NOW = datetime.now(UTC)
# Costo mínimo: las pruebas no necesitan el costo de producción.
HASHER = BcryptPasswordHasher(cost_factor=4)


class FakeUow:
    def __init__(self) -> None:
        self.commits = 0

    @property
    def session(self) -> Any:
        return None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None


class FakeUserRepo:
    def __init__(self, user: User | None) -> None:
        self.user = user
        self.saved = 0

    async def get_by_id(self, user_id: UUID) -> User | None:
        return self.user

    async def save(self, user: User) -> None:
        self.saved += 1


class FakeRefreshRepo:
    def __init__(self) -> None:
        self.revoked_for: list[UUID] = []
        self.added: list[RefreshToken] = []

    async def revoke_all_for_user(self, user_id: UUID, now: datetime) -> None:
        self.revoked_for.append(user_id)

    async def add(self, token: RefreshToken) -> None:
        self.added.append(token)


class FakeTokenIssuer:
    def new_refresh(self) -> tuple[str, str]:
        return "raw-refresh-token", "a" * 64


def _google_only_user() -> User:
    return User.register_google(
        email=Email("ana@mail.com"),
        full_name=FullName("Ana Torres"),
        google_sub="google-sub-1",
        terms_version="2026-10",
        now=NOW,
    )


def _user_with_password_and_google() -> User:
    user = _google_only_user()
    user.change_password(HASHER.hash(PlainPassword("Viajar2026")), now=NOW)
    return user


def _set_password_handler(
    user: User | None,
) -> tuple[SetPasswordHandler, FakeUserRepo, FakeUow, FakeRefreshRepo]:
    repo, uow, refresh = FakeUserRepo(user), FakeUow(), FakeRefreshRepo()
    handler = SetPasswordHandler(
        uow=cast(Any, uow),
        user_repo=cast(Any, repo),
        refresh_repo=cast(Any, refresh),
        password_hasher=HASHER,
        token_issuer=cast(Any, FakeTokenIssuer()),
    )
    return handler, repo, uow, refresh


def _unlink_handler(user: User | None) -> tuple[UnlinkGoogleHandler, FakeUserRepo, FakeUow]:
    repo, uow = FakeUserRepo(user), FakeUow()
    return UnlinkGoogleHandler(uow=cast(Any, uow), user_repo=cast(Any, repo)), repo, uow


# --- Dominio -----------------------------------------------------------------


def test_unlink_google_requires_a_password() -> None:
    user = _google_only_user()
    with pytest.raises(DomainError) as exc:
        user.unlink_google(NOW)
    assert exc.value.code == "PASSWORD_REQUIRED"
    assert user.google_sub == "google-sub-1"


def test_unlink_google_clears_link_and_keeps_password() -> None:
    user = _user_with_password_and_google()
    user.unlink_google(NOW)
    assert user.google_sub is None
    assert user.password_hash is not None
    assert user.can_login_with_password() is True


def test_unlink_google_is_idempotent_without_google() -> None:
    user = _user_with_password_and_google()
    user.unlink_google(NOW)
    user.unlink_google(NOW)
    assert user.google_sub is None


# --- Crear / cambiar contraseña ----------------------------------------------


async def test_google_only_account_creates_password_without_current() -> None:
    user = _google_only_user()
    handler, repo, uow, _ = _set_password_handler(user)

    result = await handler.handle(SetPasswordCommand(user.id.value, "Viajar2026"))

    assert result.is_success
    assert user.password_hash is not None
    assert HASHER.verify("Viajar2026", user.password_hash)
    assert user.google_sub == "google-sub-1"
    assert (repo.saved, uow.commits) == (1, 1)


async def test_existing_password_requires_current_password() -> None:
    user = _user_with_password_and_google()
    handler, repo, _, _ = _set_password_handler(user)

    result = await handler.handle(SetPasswordCommand(user.id.value, "NuevaClave2026"))

    assert result.is_failure
    assert result.error.code == "VALIDATION_ERROR"
    assert repo.saved == 0


async def test_wrong_current_password_is_rejected_and_nothing_changes() -> None:
    user = _user_with_password_and_google()
    previous = user.password_hash
    handler, repo, _, _ = _set_password_handler(user)

    result = await handler.handle(
        SetPasswordCommand(user.id.value, "NuevaClave2026", current_password="Incorrecta1")
    )

    assert result.is_failure
    assert result.error.code == "INVALID_CURRENT_PASSWORD"
    assert user.password_hash == previous
    assert repo.saved == 0


async def test_password_change_revokes_all_sessions_and_opens_a_new_one() -> None:
    user = _user_with_password_and_google()
    handler, _, uow, refresh = _set_password_handler(user)

    result = await handler.handle(
        SetPasswordCommand(user.id.value, "NuevaClave2026", current_password="Viajar2026")
    )

    assert result.is_success
    assert result.value == "raw-refresh-token"
    assert refresh.revoked_for == [user.id.value]
    assert [t.token_hash for t in refresh.added] == ["a" * 64]
    assert refresh.added[0].user_id == user.id.value
    assert uow.commits == 1


async def test_failed_change_does_not_touch_sessions() -> None:
    user = _user_with_password_and_google()
    handler, _, _, refresh = _set_password_handler(user)

    await handler.handle(
        SetPasswordCommand(user.id.value, "NuevaClave2026", current_password="Incorrecta1")
    )

    assert refresh.revoked_for == []
    assert refresh.added == []


async def test_changes_password_with_correct_current_password() -> None:
    user = _user_with_password_and_google()
    handler, _, uow, _ = _set_password_handler(user)

    result = await handler.handle(
        SetPasswordCommand(user.id.value, "NuevaClave2026", current_password="Viajar2026")
    )

    assert result.is_success
    assert user.password_hash is not None
    assert HASHER.verify("NuevaClave2026", user.password_hash)
    assert uow.commits == 1


@pytest.mark.parametrize("weak", ["corta1", "sololetrasqueesmuylarga", "1234567890"])
async def test_weak_new_password_is_a_validation_error(weak: str) -> None:
    user = _google_only_user()
    handler, repo, _, _ = _set_password_handler(user)

    result = await handler.handle(SetPasswordCommand(user.id.value, weak))

    assert result.is_failure
    assert result.error.code == "VALIDATION_ERROR"
    assert repo.saved == 0


async def test_set_password_for_missing_user_is_unauthenticated() -> None:
    handler, _, _, _ = _set_password_handler(None)
    result = await handler.handle(SetPasswordCommand(UUID(int=1), "Viajar2026"))
    assert result.is_failure
    assert result.error.code == "UNAUTHENTICATED"


# --- Desvincular Google -------------------------------------------------------


async def test_unlink_without_password_is_a_conflict_and_keeps_google() -> None:
    user = _google_only_user()
    handler, repo, _ = _unlink_handler(user)

    result = await handler.handle(UnlinkGoogleCommand(user.id.value))

    assert result.is_failure
    assert result.error.code == "PASSWORD_REQUIRED"
    assert user.google_sub == "google-sub-1"
    assert repo.saved == 0


async def test_unlink_with_password_removes_google() -> None:
    user = _user_with_password_and_google()
    handler, repo, uow = _unlink_handler(user)

    result = await handler.handle(UnlinkGoogleCommand(user.id.value))

    assert result.is_success
    assert user.google_sub is None
    assert (repo.saved, uow.commits) == (1, 1)


async def test_unlink_password_only_account_is_a_silent_success() -> None:
    user = User.register_local(
        email=Email("bea@mail.com"),
        full_name=FullName("Bea Ruiz"),
        password_hash=PasswordHash("$2b$12$abcdefghijklmnopqrstuv"),
        terms_version="2026-10",
        now=NOW,
    )
    handler, _, _ = _unlink_handler(user)
    result = await handler.handle(UnlinkGoogleCommand(user.id.value))
    assert result.is_success


# --- Refresh: un token revocado a propósito no arrastra las demás sesiones -------


async def test_refresh_with_explicitly_revoked_token_does_not_revoke_other_sessions() -> None:
    from src.modules.iam.application.commands.refresh_session import (
        RefreshSessionCommand,
        RefreshSessionHandler,
    )

    user = _user_with_password_and_google()
    revoked = RefreshToken(
        id=UUID(int=7),
        user_id=user.id.value,
        token_hash="b" * 64,
        expires_at=NOW.replace(year=NOW.year + 1),
        created_at=NOW,
        revoked_at=NOW,
        replaced_by_hash=None,
    )

    class Repo(FakeRefreshRepo):
        async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
            return revoked

    class Issuer(FakeTokenIssuer):
        def hash_token(self, raw: str) -> str:
            return "b" * 64

    refresh = Repo()
    handler = RefreshSessionHandler(
        uow=cast(Any, FakeUow()),
        user_repo=cast(Any, FakeUserRepo(user)),
        refresh_repo=cast(Any, refresh),
        token_issuer=cast(Any, Issuer()),
    )

    result = await handler.handle(RefreshSessionCommand(refresh_token="viejo"))

    assert result.is_failure
    assert result.error.code == "INVALID_REFRESH_TOKEN"
    assert refresh.revoked_for == []
