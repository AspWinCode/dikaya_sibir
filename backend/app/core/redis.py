from redis.asyncio import Redis, from_url

from app.core.config import settings

_redis: Redis | None = None


async def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = from_url(str(settings.REDIS_URL), decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        # redis-py 5.x has aclose() at runtime; its stub lags behind.
        await _redis.aclose()  # type: ignore[attr-defined]
        _redis = None
