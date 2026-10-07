"""
Health check endpoints.

GET /health        — full dependency check (DB, Redis, S3, ClamAV)
GET /health/live   — liveness probe (returns 200 immediately, no deps)
GET /health/ready  — readiness probe (DB + Redis must be up)
"""

import time
from typing import Any

import structlog
from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbDep
from app.core.config import settings
from app.schemas.common import HealthStatus

logger = structlog.get_logger(__name__)
router = APIRouter()


async def _check_database(db: DbDep) -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000, 1)}
    except Exception as exc:
        logger.error("health_db_failed", error=str(exc))
        return {"status": "error", "detail": str(exc)}


async def _check_redis() -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(str(settings.REDIS_URL), socket_connect_timeout=2)
        await client.ping()
        # redis-py 5.x has aclose() at runtime; its stub lags behind.
        await client.aclose()  # type: ignore[attr-defined]
        return {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000, 1)}
    except Exception as exc:
        logger.error("health_redis_failed", error=str(exc))
        return {"status": "error", "detail": str(exc)}


async def _check_s3() -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        import asyncio

        import boto3

        def _head() -> None:
            s3 = boto3.client(
                "s3",
                endpoint_url=settings.S3_ENDPOINT_URL,
                aws_access_key_id=settings.S3_ACCESS_KEY,
                aws_secret_access_key=settings.S3_SECRET_KEY,
            )
            s3.head_bucket(Bucket=settings.S3_BUCKET_FILES)

        await asyncio.to_thread(_head)
        return {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000, 1)}
    except Exception as exc:
        logger.warning("health_s3_failed", error=str(exc))
        return {"status": "degraded", "detail": str(exc)}


async def _check_clamav() -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        import asyncio

        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(settings.CLAMAV_HOST, settings.CLAMAV_PORT),
            timeout=2,
        )
        writer.write(b"PING\n")
        await writer.drain()
        resp = await asyncio.wait_for(reader.read(64), timeout=2)
        writer.close()
        await writer.wait_closed()
        ok = b"PONG" in resp
        return {
            "status": "ok" if ok else "degraded",
            "latency_ms": round((time.monotonic() - t0) * 1000, 1),
        }
    except Exception as exc:
        logger.warning("health_clamav_failed", error=str(exc))
        return {"status": "degraded", "detail": str(exc)}


@router.get("/health", response_model=HealthStatus, tags=["system"])
async def health(db: DbDep) -> HealthStatus:
    """Full health check — all external dependencies."""
    checks: dict[str, Any] = {}
    checks["database"] = await _check_database(db)
    checks["redis"] = await _check_redis()
    checks["s3"] = await _check_s3()
    checks["clamav"] = await _check_clamav()

    # overall: error if any critical service is down; degraded if optional is down
    critical = {"database", "redis"}
    statuses = {
        k: (v if isinstance(v, str) else v.get("status", "error")) for k, v in checks.items()
    }
    if any(statuses[k] == "error" for k in critical):
        overall = "error"
    elif any(s != "ok" for s in statuses.values()):
        overall = "degraded"
    else:
        overall = "ok"

    return HealthStatus(status=overall, version=settings.APP_VERSION, checks=checks)


@router.get("/health/live", tags=["system"])
async def liveness() -> dict[str, str]:
    """Kubernetes liveness probe — always 200 if process is running."""
    return {"status": "ok"}


@router.get("/health/ready", tags=["system"])
async def readiness(db: DbDep) -> dict[str, Any]:
    """Kubernetes readiness probe — 200 only if DB and Redis are reachable."""
    db_check = await _check_database(db)
    redis_check = await _check_redis()

    ready = db_check["status"] == "ok" and redis_check["status"] == "ok"
    return {
        "ready": ready,
        "database": db_check,
        "redis": redis_check,
    }
