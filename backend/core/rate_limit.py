from __future__ import annotations

from fastapi import HTTPException, Request

from backend.core.cache import redis_client
from backend.core.config import settings


async def check_rate_limit(key: str, max_attempts: int, window_seconds: int) -> None:
    # Use pipeline to atomically increment and set TTL, preventing infinite-TTL keys
    # on process crash between two separate Redis calls.
    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, window_seconds)
    results = await pipe.execute()
    count: int = results[0]
    if count > max_attempts:
        ttl = await redis_client.ttl(key)
        raise HTTPException(
            status_code=429,
            detail={
                "message": f"Too many attempts. Try again in {ttl} seconds.",
                "retry_after": ttl,
            },
            headers={"Retry-After": str(ttl)},
        )


def auth_rate_limit_key(request: Request, email: str) -> str:
    client_ip = request.client.host if request.client else "unknown"
    return f"rate_limit:auth:{client_ip}:{email}"


async def rate_limit_request(
    request: Request,
    *,
    bucket: str,
    max_attempts: int | None = None,
    window_seconds: int | None = None,
) -> None:
    client_ip = request.client.host if request.client else "unknown"
    key = f"rate_limit:{bucket}:{client_ip}:{request.url.path}"
    await check_rate_limit(
        key,
        max_attempts or settings.RATE_LIMIT_DEFAULT_MAX_ATTEMPTS,
        window_seconds or settings.RATE_LIMIT_DEFAULT_WINDOW_SECONDS,
    )
