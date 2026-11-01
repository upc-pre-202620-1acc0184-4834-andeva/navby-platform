import hashlib
import hmac
from typing import Any, cast
from uuid import UUID

from redis.asyncio import Redis

from src.modules.iam.application.acl.ports.one_time_code_store import (
    OneTimeCodeStore,
    OtpCheck,
)


class RedisOneTimeCodeStore(OneTimeCodeStore):
    def __init__(self, redis: Redis) -> None:
        self._redis: Any = redis

    async def save_otp(self, user_id: UUID, code_hash: str) -> None:
        key = f"navby:iam:verify:{user_id}"
        await self._redis.hset(key, mapping={"code_hash": code_hash, "attempts": "0"})
        await self._redis.expire(key, 600)

    async def check_otp(self, user_id: UUID, code: str) -> OtpCheck:
        key = f"navby:iam:verify:{user_id}"
        data = cast(dict[str, str], await self._redis.hgetall(key))
        if not data:
            return OtpCheck.INVALID

        attempts = int(data.get("attempts", "0"))
        if attempts >= 5:
            await self._redis.delete(key)
            return OtpCheck.EXHAUSTED

        candidate_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
        stored_hash = str(data.get("code_hash", ""))
        if hmac.compare_digest(candidate_hash, stored_hash):
            await self._redis.delete(key)
            return OtpCheck.VALID

        new_attempts = int(await self._redis.hincrby(key, "attempts", 1))
        if new_attempts >= 5:
            await self._redis.delete(key)
            return OtpCheck.EXHAUSTED
        return OtpCheck.INVALID

    async def can_resend_otp(self, email_hash: str) -> bool:
        key = f"navby:iam:verify_resend:{email_hash}"
        return int(await self._redis.exists(key)) == 0

    async def mark_resend_otp(self, email_hash: str) -> None:
        key = f"navby:iam:verify_resend:{email_hash}"
        await self._redis.set(key, "1", ex=60)

    async def save_reset(self, token_hash: str, user_id: UUID) -> None:
        key = f"navby:iam:reset:{token_hash}"
        await self._redis.set(key, str(user_id), ex=1800)

    async def peek_reset(self, token_hash: str) -> UUID | None:
        key = f"navby:iam:reset:{token_hash}"
        val = await self._redis.get(key)
        if not val:
            return None
        return UUID(str(val))

    async def consume_reset(self, token_hash: str) -> UUID | None:
        key = f"navby:iam:reset:{token_hash}"
        val = await self._redis.get(key)
        if not val:
            return None
        await self._redis.delete(key)
        return UUID(str(val))
