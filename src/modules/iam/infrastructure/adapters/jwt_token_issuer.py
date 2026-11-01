import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt

from src.modules.iam.application.acl.ports.token_issuer import TokenIssuer
from src.modules.iam.domain.model.aggregates.user import User


class JwtTokenIssuer(TokenIssuer):
    def __init__(self, secret: str, access_ttl_seconds: int = 900) -> None:
        self._secret = secret
        self._access_ttl_seconds = access_ttl_seconds

    def issue_access(self, user: User) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user.id.value),
            "email": user.email.value,
            "ev": user.email_verified,
            "email_verified": user.email_verified,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=self._access_ttl_seconds)).timestamp()),
        }
        return jwt.encode(payload, self._secret, algorithm="HS256")

    def new_refresh(self) -> tuple[str, str]:
        raw = secrets.token_urlsafe(32)
        return raw, self.hash_token(raw)

    def hash_token(self, raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
