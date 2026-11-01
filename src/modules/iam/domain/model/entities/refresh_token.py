from datetime import datetime
from uuid import UUID


class RefreshToken:
    def __init__(
        self,
        id: UUID,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
        created_at: datetime,
        revoked_at: datetime | None = None,
        replaced_by_hash: str | None = None,
    ) -> None:
        self.id = id
        self.user_id = user_id
        self.token_hash = token_hash
        self.expires_at = expires_at
        self.created_at = created_at
        self.revoked_at = revoked_at
        self.replaced_by_hash = replaced_by_hash

    def is_active(self, now: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now

    def rotate(self, new_hash: str, now: datetime) -> None:
        self.revoked_at = now
        self.replaced_by_hash = new_hash

    def revoke(self, now: datetime) -> None:
        if self.revoked_at is None:
            self.revoked_at = now
