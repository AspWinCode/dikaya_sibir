"""
Rate limiting via slowapi + Redis.

Key function: authenticated requests keyed by user_id (from JWT sub claim),
unauthenticated requests keyed by client IP.

Default global limit: 300 requests / minute.
Sensitive overrides (applied via @limiter.limit decorator):
  - /auth/login, /auth/refresh  → 10/minute  (brute-force protection)
  - File upload endpoints       → 20/minute
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Callable

from fastapi import Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

_DEFAULT_LIMITS: list[str | Callable[..., str]] = ["300/minute"]


def _extract_user_key(request: Request) -> str:
    """
    Build a rate-limit bucket key.

    For authenticated requests: "user:<sub>" extracted from the JWT payload
    (decoded without signature verification — just for bucketing, not auth).
    For anonymous requests: "ip:<client_ip>".
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            token = auth[7:]
            # JWT payload is the second segment, base64url-encoded
            raw = token.split(".")[1]
            # Restore padding
            raw += "=" * (-len(raw) % 4)
            claims = json.loads(base64.b64decode(raw))
            sub = claims.get("sub")
            if sub:
                return f"user:{sub}"
        except Exception:
            # Malformed/missing JWT just falls back to IP bucketing below —
            # expected for anonymous or stale-token requests, so debug-only.
            logger.debug("rate_limit_key_jwt_decode_failed", exc_info=True)
    ip = request.client.host if request.client else "unknown"
    return f"ip:{ip}"


# Single limiter instance — imported by main.py and endpoint modules
limiter = Limiter(
    key_func=_extract_user_key,
    default_limits=_DEFAULT_LIMITS,
    # Use Redis as storage backend (URL set via CELERY_BROKER_URL / REDIS_URL env)
    # slowapi falls back to in-memory if Redis is unavailable (dev-friendly)
    storage_uri=None,  # resolved in main.py from settings
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """RFC 7807 response for 429 Too Many Requests."""
    return JSONResponse(
        status_code=429,
        content={
            "title": "Too Many Requests",
            "status": 429,
            "detail": str(exc.detail),
            "instance": str(request.url),
        },
        headers={"Retry-After": str(getattr(exc, "retry_after", 60))},
        media_type="application/problem+json",
    )
