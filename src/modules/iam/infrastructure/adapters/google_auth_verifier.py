import asyncio
import logging

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from src.modules.iam.application.acl.ports.google_identity_verifier import (
    GoogleIdentity,
    GoogleIdentityVerifier,
)

logger = logging.getLogger(__name__)


class GoogleAuthVerifier(GoogleIdentityVerifier):
    def __init__(self, client_id: str) -> None:
        self._client_id = client_id

    def _verify_sync(self, token: str) -> GoogleIdentity | None:
        if not self._client_id:
            return None
        try:
            info = google_id_token.verify_oauth2_token(
                token,
                google_requests.Request(),  # type: ignore[no-untyped-call]
                self._client_id,
            )
            return GoogleIdentity(
                sub=str(info["sub"]),
                email=str(info["email"]),
                email_verified=bool(info.get("email_verified", False)),
                name=str(info.get("name") or info["email"].split("@")[0]),
            )
        except Exception as exc:
            logger.warning("Google token verification failed: %s", exc)
            return None

    async def verify(self, id_token: str) -> GoogleIdentity | None:
        return await asyncio.to_thread(self._verify_sync, id_token)
