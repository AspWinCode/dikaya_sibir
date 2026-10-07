from typing import Annotated
from uuid import UUID

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
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
    return CurrentUser(
        user_id=UUID(payload["sub"]),
        roles=payload.get("roles", []),
        org_id=UUID(raw_org) if raw_org else None,
        email=payload.get("email"),
    )


AuthDep = Annotated[CurrentUser, Depends(get_current_user)]
