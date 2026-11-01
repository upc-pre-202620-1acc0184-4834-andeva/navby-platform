from datetime import datetime
from uuid import uuid4

from src.modules.iam.domain.model.events.user_deleted import UserDeleted
from src.modules.iam.domain.model.events.user_verified import UserVerified
from src.modules.iam.domain.model.value_objects.email import Email
from src.modules.iam.domain.model.value_objects.full_name import FullName
from src.modules.iam.domain.model.value_objects.password_hash import PasswordHash
from src.modules.iam.domain.model.value_objects.user_id import UserId
from src.shared.domain.aggregate_root import AggregateRoot
from src.shared.domain.domain_error import DomainError


class User(AggregateRoot):
    def __init__(
        self,
        id: UserId,
        email: Email,
        full_name: FullName,
        password_hash: PasswordHash | None,
        google_sub: str | None,
        email_verified: bool,
        terms_version: str,
        terms_accepted_at: datetime,
        created_at: datetime,
        updated_at: datetime,
        deleted_at: datetime | None = None,
    ) -> None:
        super().__init__()
        self.id = id
        self.email = email
        self.full_name = full_name
        self.password_hash = password_hash
        self.google_sub = google_sub
        self.email_verified = email_verified
        self.terms_version = terms_version
        self.terms_accepted_at = terms_accepted_at
        self.created_at = created_at
        self.updated_at = updated_at
        self.deleted_at = deleted_at

    @staticmethod
    def register_local(
        email: Email,
        full_name: FullName,
        password_hash: PasswordHash,
        terms_version: str,
        now: datetime,
    ) -> "User":
        return User(
            id=UserId(uuid4()),
            email=email,
            full_name=full_name,
            password_hash=password_hash,
            google_sub=None,
            email_verified=False,
            terms_version=terms_version,
            terms_accepted_at=now,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )

    @staticmethod
    def register_google(
        email: Email,
        full_name: FullName,
        google_sub: str,
        terms_version: str,
        now: datetime,
    ) -> "User":
        user = User(
            id=UserId(uuid4()),
            email=email,
            full_name=full_name,
            password_hash=None,
            google_sub=google_sub,
            email_verified=True,
            terms_version=terms_version,
            terms_accepted_at=now,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        user.record_event(
            UserVerified(
                event_id=uuid4(),
                occurred_at=now,
                user_id=user.id.value,
            )
        )
        return user

    def verify_email(self, now: datetime) -> None:
        if self.deleted_at is not None:
            raise DomainError("INVALID_OTP", "Account is deleted.")
        if self.email_verified:
            return
        self.email_verified = True
        self.updated_at = now
        self.record_event(
            UserVerified(
                event_id=uuid4(),
                occurred_at=now,
                user_id=self.id.value,
            )
        )

    def link_google(self, google_sub: str, now: datetime) -> None:
        if self.deleted_at is not None:
            raise DomainError("INVALID_CREDENTIALS", "Account is deleted.")
        if not self.email_verified:
            self.password_hash = None
            self.google_sub = google_sub
            self.email_verified = True
            self.updated_at = now
            self.record_event(
                UserVerified(
                    event_id=uuid4(),
                    occurred_at=now,
                    user_id=self.id.value,
                )
            )
        else:
            self.google_sub = google_sub
            self.updated_at = now

    def change_password(self, password_hash: PasswordHash, now: datetime) -> None:
        if self.deleted_at is not None:
            raise DomainError("INVALID_RESET_TOKEN", "Account is deleted.")
        was_verified = self.email_verified
        self.password_hash = password_hash
        self.email_verified = True
        self.updated_at = now
        if not was_verified:
            self.record_event(
                UserVerified(
                    event_id=uuid4(),
                    occurred_at=now,
                    user_id=self.id.value,
                )
            )

    def can_login_with_password(self) -> bool:
        return self.deleted_at is None and self.password_hash is not None and self.email_verified

    def delete(self, now: datetime) -> None:
        if self.deleted_at is not None:
            return
        self.email = Email(f"deleted-{self.id.value}@navby.invalid")
        self.full_name = FullName("Usuario eliminado")
        self.password_hash = None
        self.google_sub = None
        self.deleted_at = now
        self.updated_at = now
        self.record_event(
            UserDeleted(
                event_id=uuid4(),
                occurred_at=now,
                user_id=self.id.value,
            )
        )
