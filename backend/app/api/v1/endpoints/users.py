import uuid

import structlog
from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AuthDep, DbDep
from app.core.config import settings
from app.schemas.auth import SessionRead
from app.schemas.common import CursorPage
from app.schemas.users import (
    AdminSetPasswordRequest,
    AuditLogRead,
    InviteUserRequest,
    InviteUserResult,
    RoleRead,
    UserCreate,
    UserListParams,
    UserRead,
    UserUpdate,
)
from app.services.session_policy import SessionPolicyService
from app.services.users import UserConflictError, UserNotFoundError, UserService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


def _require_admin(current_user: AuthDep) -> None:
    if not current_user.has_role("platform_admin") and not current_user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )


@router.get("", response_model=CursorPage[UserRead], summary="List users (cursor pagination)")
async def list_users(
    current_user: AuthDep,
    db: DbDep,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    search: str | None = Query(default=None),
    role: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
) -> CursorPage[UserRead]:
    if not current_user.has_role("platform_admin", "auditor", "org_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    params = UserListParams(
        cursor=cursor, limit=limit, search=search, role=role, is_active=is_active
    )
    # org_admin sees only their org; platform_admin/auditor see all
    actor_org_id = (
        current_user.org_id if not current_user.has_role("platform_admin", "auditor") else None
    )
    return await UserService(db).list_users(params, actor_org_id=actor_org_id)


@router.post(
    "", response_model=UserRead, status_code=status.HTTP_201_CREATED, summary="Create user"
)
async def create_user(body: UserCreate, current_user: AuthDep, db: DbDep) -> UserRead:
    if not current_user.has_role("platform_admin", "org_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    try:
        return await UserService(db).create_user(
            body,
            granted_by=current_user.user_id,
            actor_email=current_user.email if hasattr(current_user, "email") else None,
            actor_org_id=current_user.org_id if current_user.is_org_admin else None,
        )
    except UserConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post(
    "/invite",
    response_model=InviteUserResult,
    status_code=status.HTTP_201_CREATED,
    summary="Invite user by email (sends invitation email with temp password)",
)
async def invite_user(
    body: InviteUserRequest, current_user: AuthDep, db: DbDep
) -> InviteUserResult:
    if not current_user.has_role("platform_admin", "org_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    try:
        user, temp_password = await UserService(db).invite_user(
            body,
            granted_by=current_user.user_id,
            actor_email=getattr(current_user, "email", None),
            actor_org_id=current_user.org_id if current_user.is_org_admin else None,
        )
    except UserConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    # The user row is already flushed (constraint errors surfaced above). Sent
    # synchronously so the admin learns the outcome and gets the temp password
    # back if delivery failed.
    from app.services.email import send_invitation_email

    sent = await send_invitation_email(
        body.email, body.display_name, temp_password, settings.FRONTEND_URL, db=db
    )
    if not sent:
        logger.warning("invitation_email_not_sent", user_id=str(user.id), email=body.email)
    return InviteUserResult(
        **user.model_dump(),
        email_sent=sent,
        temp_password=None if sent else temp_password,
    )


@router.get("/me", response_model=UserRead, summary="Get current user profile")
async def me(current_user: AuthDep, db: DbDep) -> UserRead:
    try:
        return await UserService(db).get_by_id(current_user.user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found") from exc


@router.get(
    "/roles",
    response_model=list[RoleRead],
    tags=["roles"],
    summary="List all roles (deprecated, use GET /roles)",
)
async def list_roles(current_user: AuthDep, db: DbDep) -> list[RoleRead]:
    from app.services.roles import RoleService

    return await RoleService(db).list_roles()


@router.get("/{user_id}", response_model=UserRead, summary="Get user by ID")
async def get_user(user_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> UserRead:
    if user_id != current_user.user_id and not current_user.has_role(
        "platform_admin", "auditor", "org_admin"
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    try:
        user = await UserService(db).get_by_id(user_id)
        # org_admin can only see users in their own org
        if (
            current_user.is_org_admin
            and not current_user.is_platform_admin
            and user.id != current_user.user_id
            and user.org_id != current_user.org_id
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        return user
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc


@router.patch("/{user_id}", response_model=UserRead, summary="Update user")
async def update_user(
    user_id: uuid.UUID, body: UserUpdate, current_user: AuthDep, db: DbDep
) -> UserRead:
    if not current_user.has_role("platform_admin", "org_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    try:
        return await UserService(db).update_user(
            user_id,
            body,
            updated_by=current_user.user_id,
            actor_org_id=current_user.org_id if current_user.is_org_admin else None,
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.delete(
    "/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Deactivate user (soft)"
)
async def delete_user(user_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> None:
    if not current_user.has_role("platform_admin", "org_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    try:
        await UserService(db).delete_user(
            user_id,
            deleted_by=current_user.user_id,
            actor_org_id=current_user.org_id if current_user.is_org_admin else None,
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post(
    "/{user_id}/set-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Admin: set password directly without email",
)
async def admin_set_password(
    user_id: uuid.UUID, body: AdminSetPasswordRequest, current_user: AuthDep, db: DbDep
) -> None:
    if not current_user.has_role("platform_admin", "org_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    try:
        await UserService(db).set_password(
            user_id,
            body.new_password,
            set_by=current_user.user_id,
            actor_email=getattr(current_user, "email", None),
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get(
    "/{user_id}/sessions",
    response_model=list[SessionRead],
    summary="List active sessions for a user",
)
async def list_user_sessions(
    user_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> list[SessionRead]:
    if user_id != current_user.user_id and not current_user.has_role("platform_admin", "org_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    return await SessionPolicyService(db).list_sessions(user_id=user_id)


@router.delete(
    "/{user_id}/sessions",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Terminate all sessions for a user (admin)",
)
async def terminate_user_sessions(user_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> None:
    if user_id != current_user.user_id and not current_user.has_role("platform_admin", "org_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    await SessionPolicyService(db).terminate_all_for_user(user_id)


@router.delete(
    "/{user_id}/hard",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete user from database",
)
async def hard_delete_user(user_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> None:
    if not current_user.has_role("platform_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform_admin can hard-delete users",
        )
    try:
        await UserService(db).hard_delete_user(
            user_id,
            deleted_by=current_user.user_id,
            actor_email=getattr(current_user, "email", None),
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get(
    "/sessions", response_model=list[SessionRead], summary="List all active sessions (admin)"
)
async def list_all_sessions(
    current_user: AuthDep,
    db: DbDep,
    limit: int = Query(default=200, ge=1, le=500),
) -> list[SessionRead]:
    if not current_user.has_role("platform_admin", "org_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    return await SessionPolicyService(db).list_sessions(limit=limit)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Force-terminate a specific session (admin)",
)
async def terminate_session(session_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> None:
    if not current_user.has_role("platform_admin", "org_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    ok = await SessionPolicyService(db).terminate(session_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or already revoked"
        )


@router.get("/audit-logs", response_model=list[AuditLogRead], summary="Get audit log (admin only)")
async def get_audit_logs(
    current_user: AuthDep,
    db: DbDep,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    level: str | None = Query(default=None),
    action: str | None = Query(default=None),
) -> list[AuditLogRead]:
    if not current_user.has_role("platform_admin", "auditor", "org_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    # org_admin sees only their org's logs; platform_admin/auditor see all
    org_id = (
        current_user.org_id
        if current_user.has_role("org_admin")
        and not current_user.has_role("platform_admin", "auditor")
        else None
    )
    return await UserService(db).list_audit_logs(
        limit=limit, offset=offset, level=level, action=action, org_id=org_id
    )
