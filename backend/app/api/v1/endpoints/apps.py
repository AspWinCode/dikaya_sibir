import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.asyncio import Redis

from app.api.deps import AuthDep, DbDep
from app.core.locks import EditLock, LockConflictError
from app.core.redis import get_redis
from app.schemas.apps import (
    AppCloneCreate,
    AppCreate,
    AppMemberAdd,
    AppMemberRead,
    AppRead,
    AppSnapshotCreate,
    AppSnapshotRead,
    AppUpdate,
    LockInfo,
    PublishCheckResult,
)
from app.schemas.common import CursorPage
from app.schemas.records import TrashedRecordRead
from app.services.apps import (
    AppConflictError,
    AppNotFoundError,
    AppPermissionError,
    AppPublishBlockedError,
    AppService,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/apps", tags=["apps"])

RedisDep = Annotated[Redis, Depends(get_redis)]


def _svc(db: DbDep) -> AppService:
    return AppService(db)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")


@router.get("", response_model=CursorPage[AppRead])
async def list_apps(
    current_user: AuthDep,
    db: DbDep,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    search: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
) -> CursorPage[AppRead]:
    return await AppService(db).list_apps(
        actor_id=current_user.user_id,
        cursor=cursor,
        limit=limit,
        search=search,
        include_archived=include_archived,
        actor_org_id=current_user.org_id,
    )


@router.post("", response_model=AppRead, status_code=status.HTTP_201_CREATED)
async def create_app(body: AppCreate, current_user: AuthDep, db: DbDep) -> AppRead:
    if not current_user.has_role("platform_admin", "app_builder", "org_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    try:
        return await AppService(db).create_app(
            body, owner_id=current_user.user_id, org_id=current_user.org_id
        )
    except AppConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/{app_id}", response_model=AppRead)
async def get_app(app_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> AppRead:
    try:
        return await AppService(db).get_app(
            app_id, actor_id=current_user.user_id,
        )
    except AppNotFoundError as exc:
        raise _not_found() from exc


@router.patch("/{app_id}", response_model=AppRead)
async def update_app(
    app_id: uuid.UUID, body: AppUpdate, current_user: AuthDep, db: DbDep, redis: RedisDep
) -> AppRead:
    lock = EditLock(
        redis, "app", app_id, current_user.user_id,
        holder_name=str(current_user.user_id),
    )
    try:
        async with lock:
            return await AppService(db).update_app(
                app_id, body,
                actor_id=current_user.user_id,
            )
    except LockConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={"holder_id": exc.holder_id, "holder_name": exc.holder_name},
        ) from exc
    except AppNotFoundError as exc:
        raise _not_found() from exc
    except AppPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_app(app_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> None:
    try:
        await AppService(db).delete_app(
            app_id, actor_id=current_user.user_id,
        )
    except AppNotFoundError as exc:
        raise _not_found() from exc
    except AppPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/{app_id}/publish/check", response_model=PublishCheckResult)
async def check_publish(app_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> PublishCheckResult:
    """Dry-run the pre-publish integrity check (ТЗ 3.11.1) — lets the editor
    show issues before the user commits to publishing."""
    try:
        return await AppService(db).check_publish(app_id)
    except AppNotFoundError as exc:
        raise _not_found() from exc


@router.post("/{app_id}/publish", response_model=AppRead)
async def publish_app(app_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> AppRead:
    try:
        return await AppService(db).publish_app(
            app_id, actor_id=current_user.user_id,
        )
    except AppNotFoundError as exc:
        raise _not_found() from exc
    except AppPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except AppPublishBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Публикация заблокирована — устраните критические ошибки",
                "issues": [i.model_dump() for i in exc.issues],
            },
        ) from exc


# ---- Clone ----

@router.post("/{app_id}/clone", response_model=AppRead, status_code=status.HTTP_201_CREATED)
async def clone_app(
    app_id: uuid.UUID, body: AppCloneCreate, current_user: AuthDep, db: DbDep
) -> AppRead:
    try:
        return await AppService(db).clone_app(
            app_id,
            body,
            owner_id=current_user.user_id,
            org_id=current_user.org_id,
        )
    except AppNotFoundError as exc:
        raise _not_found() from exc
    except AppConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AppPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


# ---- Snapshots ----

@router.get("/{app_id}/snapshots", response_model=list[AppSnapshotRead])
async def list_snapshots(
    app_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> list[AppSnapshotRead]:
    try:
        return await AppService(db).list_snapshots(
            app_id,
            actor_id=current_user.user_id,
        )
    except AppNotFoundError as exc:
        raise _not_found() from exc
    except AppPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post("/{app_id}/snapshots", response_model=AppSnapshotRead, status_code=status.HTTP_201_CREATED)
async def create_snapshot(
    app_id: uuid.UUID, body: AppSnapshotCreate, current_user: AuthDep, db: DbDep
) -> AppSnapshotRead:
    try:
        return await AppService(db).create_snapshot(
            app_id,
            body,
            actor_id=current_user.user_id,
        )
    except AppNotFoundError as exc:
        raise _not_found() from exc
    except AppPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post(
    "/{app_id}/snapshots/{snapshot_num}/rollback",
    response_model=AppRead,
)
async def rollback_snapshot(
    app_id: uuid.UUID, snapshot_num: int, current_user: AuthDep, db: DbDep
) -> AppRead:
    try:
        return await AppService(db).rollback_snapshot(
            app_id,
            snapshot_num,
            actor_id=current_user.user_id,
        )
    except AppNotFoundError as exc:
        raise _not_found() from exc
    except AppPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


# ---- Members ----

@router.get("/{app_id}/members", response_model=list[AppMemberRead])
async def list_members(app_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> list[AppMemberRead]:
    try:
        return await AppService(db).list_members(
            app_id,
            actor_id=current_user.user_id,
        )
    except AppNotFoundError as exc:
        raise _not_found() from exc
    except AppPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post("/{app_id}/members", status_code=status.HTTP_204_NO_CONTENT)
async def add_member(app_id: uuid.UUID, body: AppMemberAdd, current_user: AuthDep, db: DbDep) -> None:
    try:
        await AppService(db).add_member(
            app_id, body,
            actor_id=current_user.user_id,
        )
    except AppNotFoundError as exc:
        raise _not_found() from exc
    except AppPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.delete("/{app_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    app_id: uuid.UUID, user_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> None:
    try:
        await AppService(db).remove_member(
            app_id, user_id,
            actor_id=current_user.user_id,
        )
    except AppNotFoundError as exc:
        raise _not_found() from exc
    except AppPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


# ---- Recycle bin (ТЗ 3.9.1) ----

@router.get("/{app_id}/recycle-bin", response_model=CursorPage[TrashedRecordRead])
async def list_recycle_bin(
    app_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
    entity_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
) -> CursorPage[TrashedRecordRead]:
    """Admin-only, app-wide view of soft-deleted records across every entity —
    the DELETE endpoint's include_deleted=true mixes deleted rows into one
    entity's normal listing; this is a dedicated «Корзина» view."""
    if not current_user.has_role("platform_admin", "app_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Recycle bin access requires an admin role")
    try:
        await _svc(db).get_app(
            app_id, actor_id=current_user.user_id,
        )
    except AppNotFoundError as exc:
        raise _not_found() from exc

    from app.services.records import RecordService
    return await RecordService(db).list_deleted_records(
        app_id, entity_id=entity_id, limit=limit, cursor=cursor,
    )


# ---- Edit lock (heartbeat / status) ----

@router.get("/{app_id}/lock", response_model=LockInfo | None, tags=["locks"])
async def get_lock_info(app_id: uuid.UUID, current_user: AuthDep, redis: RedisDep) -> LockInfo | None:
    lock = EditLock(redis, "app", app_id, current_user.user_id)
    info = await lock.get_info()
    if info is None:
        return None
    return LockInfo(**info)


@router.post("/{app_id}/lock", status_code=status.HTTP_204_NO_CONTENT, tags=["locks"])
async def acquire_lock(app_id: uuid.UUID, current_user: AuthDep, redis: RedisDep) -> None:
    lock = EditLock(redis, "app", app_id, current_user.user_id)
    try:
        await lock.acquire()
    except LockConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={"holder_id": exc.holder_id},
        ) from exc


@router.delete("/{app_id}/lock", status_code=status.HTTP_204_NO_CONTENT, tags=["locks"])
async def release_lock(app_id: uuid.UUID, current_user: AuthDep, redis: RedisDep) -> None:
    lock = EditLock(redis, "app", app_id, current_user.user_id)
    await lock.release()
