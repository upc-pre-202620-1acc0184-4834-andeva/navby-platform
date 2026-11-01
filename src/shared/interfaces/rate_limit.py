import time
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis

from src.shared.application.application_error import ApplicationError
from src.shared.application.current_user import CurrentUser
from src.shared.infrastructure.redis_client import get_shared_redis
from src.shared.infrastructure.settings import Settings, get_settings
from src.shared.interfaces.auth import get_current_user
from src.shared.interfaces.http_errors import ProblemHttpError

KeyFn = Callable[[Request, Settings], str]


def client_ip_key(request: Request, settings: Settings) -> str:
    if settings.trust_proxy_headers:
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            first_ip = forwarded_for.split(",")[0].strip()
            if first_ip:
                return first_ip
    if request.client is not None and request.client.host:
        return request.client.host
    return "127.0.0.1"


def user_id_key(request: Request, settings: Settings) -> str:
    current_user: CurrentUser | None = getattr(request.state, "current_user", None)
    if current_user is not None:
        return str(current_user.user_id)
    return client_ip_key(request, settings)


def rate_limit(
    scope: str,
    key_fn: KeyFn,
    limit: int,
) -> Callable[..., Awaitable[None]]:
    async def dependency(
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)],
        redis: Annotated[Redis, Depends(get_shared_redis)],
    ) -> None:
        if key_fn is user_id_key and not hasattr(request.state, "current_user"):
            await get_current_user(request, settings)
        key = key_fn(request, settings)
        now = int(time.time())
        window = now // 60
        redis_key = f"navby:ratelimit:{scope}:{key}:{window}"
        count = int(await redis.incr(redis_key))
        if count == 1:
            await redis.expire(redis_key, 60)
        if count > limit:
            retry_after = max(1, 60 - (now % 60))
            raise ProblemHttpError(
                error=ApplicationError(
                    code="RATE_LIMITED",
                    message="Se superó el límite de peticiones por minuto.",
                ),
                instance=request.url.path,
                headers={"Retry-After": str(retry_after)},
            )

    return dependency
