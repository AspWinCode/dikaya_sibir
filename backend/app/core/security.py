import uuid as _uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _build_token(subject: str, extra: dict[str, Any], expire_delta: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + expire_delta,
        **extra,
    }
    return jwt.encode(payload, settings.JWT_PRIVATE_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(
    user_id: UUID,
    roles: list[str],
    org_id: UUID | None = None,
    email: str | None = None,
    must_change_password: bool = False,
) -> str:
    extra: dict[str, Any] = {"type": "access", "roles": roles, "jti": str(_uuid.uuid4())}
    if must_change_password:
        extra["pwd_change"] = True
    if org_id is not None:
        extra["org_id"] = str(org_id)
    if email is not None:
        extra["email"] = email
    return _build_token(
        subject=str(user_id),
        extra=extra,
        expire_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: UUID) -> str:
    return _build_token(
        subject=str(user_id),
        extra={"type": "refresh", "jti": str(_uuid.uuid4())},
        expire_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> dict[str, Any]:
    """Raises JWTError on invalid/expired token."""
    return jwt.decode(
        token,
        settings.JWT_PUBLIC_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )


__all__ = [
    "JWTError",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "hash_password",
    "verify_password",
]
