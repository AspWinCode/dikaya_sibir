import uuid

import structlog
from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import AuthDep, DbDep
from app.core.rate_limit import limiter
from app.schemas.auth import TokenPair
from app.schemas.invites import (
    InviteAcceptResult,
    InviteLinkCreate,
    InviteLinkCreated,
    InviteLinkRead,
    InvitePreview,
    InviteSignupRequest,
)
from app.services.apps import AppNotFoundError, AppPermissionError
from app.services.invites import (
    InviteConflictError,
    InviteInvalidError,
    InviteService,
    InviteSignupDisabledError,
)

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["invites"])


def _invalid() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_410_GONE, detail="Invite link is invalid or expired"
    )


# ---- Management: /apps/{app_id}/invite-links ----


@router.post(
    "/apps/{app_id}/invite-links",
    response_model=InviteLinkCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create shareable invite link (token returned once)",
)
async def create_invite_link(
    app_id: uuid.UUID, body: InviteLinkCreate, current_user: AuthDep, db: DbDep
) -> InviteLinkCreated:
    try:
        return await InviteService(db).create_link(app_id, body, actor_id=current_user.user_id)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found") from exc
    except AppPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get(
    "/apps/{app_id}/invite-links",
    response_model=list[InviteLinkRead],
    summary="List active invite links",
)
async def list_invite_links(
    app_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> list[InviteLinkRead]:
    try:
        return await InviteService(db).list_links(app_id, actor_id=current_user.user_id)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found") from exc
    except AppPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.delete(
    "/apps/{app_id}/invite-links/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke invite link",
)
async def revoke_invite_link(
    app_id: uuid.UUID, link_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> None:
    try:
        await InviteService(db).revoke_link(app_id, link_id, actor_id=current_user.user_id)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found") from exc
    except AppPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


# ---- Public flow: /invites/{token} ----


@router.get("/invites/{token}", response_model=InvitePreview, summary="Preview invite (public)")
@limiter.limit("30/minute")
async def preview_invite(token: str, request: Request, db: DbDep) -> InvitePreview:
    try:
        return await InviteService(db).preview(token)
    except InviteInvalidError as exc:
        raise _invalid() from exc


@router.post(
    "/invites/{token}/accept", response_model=InviteAcceptResult, summary="Join app as current user"
)
async def accept_invite(token: str, current_user: AuthDep, db: DbDep) -> InviteAcceptResult:
    try:
        return await InviteService(db).accept(
            token, current_user.user_id, actor_email=current_user.email
        )
    except InviteInvalidError as exc:
        raise _invalid() from exc


@router.post(
    "/invites/{token}/signup",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account via invite link and join the app",
)
@limiter.limit("5/minute")
async def signup_via_invite(
    token: str, body: InviteSignupRequest, request: Request, db: DbDep
) -> TokenPair:
    try:
        return await InviteService(db).signup(
            token,
            body,
            user_agent=request.headers.get("user-agent"),
            ip=request.client.host if request.client else None,
        )
    except InviteInvalidError as exc:
        raise _invalid() from exc
    except InviteSignupDisabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Signup via this link is disabled"
        ) from exc
    except InviteConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
