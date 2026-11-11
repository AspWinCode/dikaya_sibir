from typing import Annotated
from uuid import UUID

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.core.permissions import Overrides, user_can
from app.core.security import decode_token

logger = structlog.get_logger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)

DbDep = Annotated[AsyncSession, Depends(get_db)]
BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


class CurrentUser:
    """Parsed JWT claims attached to the request."""

    def __init__(
        self, user_id: UUID, roles: list[str], org_id: UUID | None = None, email: str | None = None
    ) -> None:
        self.user_id = user_id
        self.roles = roles
        self.org_id = org_id
        self.email = email
        # Per-role function overrides, filled in by get_current_user (see
        # app.core.permissions). Empty = built-in defaults only.
        self.function_overrides: Overrides = {}

    def can(self, function_code: str) -> bool:
        """May this user use the given function (see app.core.permissions)?"""
        return user_can(self.roles, function_code, self.function_overrides)

    def has_role(self, *roles: str) -> bool:
        return bool(set(self.roles) & set(roles))

    @property
    def is_platform_admin(self) -> bool:
        return "platform_admin" in self.roles

    @property
    def is_org_admin(self) -> bool:
        return "org_admin" in self.roles


# Endpoints still reachable while a password change is pending (temp password).
_PWD_CHANGE_ALLOWED = (
    "/api/v1/auth/change-password",
    "/api/v1/auth/logout",
    "/api/v1/auth/logout-all",
    "/api/v1/auth/password-policy",
    "/api/v1/users/me",
)


async def get_current_user(request: Request, credentials: BearerDep) -> CurrentUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials)
    except JWTError as exc:
        logger.warning("invalid_jwt", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if payload.get("pwd_change") and request.url.path not in _PWD_CHANGE_ALLOWED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password change required",
        )

    raw_org = payload.get("org_id")
    user = CurrentUser(
        user_id=UUID(payload["sub"]),
        roles=payload.get("roles", []),
        org_id=UUID(raw_org) if raw_org else None,
        email=payload.get("email"),
    )
    # Only roles other than the locked platform_admin can have overrides, so
    # a platform admin's requests never touch the database here.
    from app.services.function_permissions import load_overrides

    try:
        async with AsyncSessionLocal() as session:
            user.function_overrides = await load_overrides(session, user.roles)
    except Exception:  # noqa: BLE001 - never lock everyone out over a lookup failure
        logger.exception("function_overrides_load_failed")
    return user


AuthDep = Annotated[CurrentUser, Depends(get_current_user)]
