import uuid

import structlog
from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AuthDep, DbDep
from app.schemas.ui import (
    PageCreate,
    PageNavReorder,
    PagePermissionsSet,
    PageRead,
    PageRolePermissionRead,
    PageUpdate,
    ViewCreate,
    ViewFieldConfigBulkUpdate,
    ViewFieldConfigRead,
    ViewRead,
    ViewUpdate,
)
from app.services.apps import AppNotFoundError, AppService
from app.services.block_validation import BlockConfigError
from app.services.ui import (
    PageNotFoundError,
    PageSlugConflictError,
    UIService,
    ViewNotFoundError,
)

logger = structlog.get_logger(__name__)

# Two routers: views are entity-scoped, pages are app-scoped
views_router = APIRouter(
    prefix="/apps/{app_id}/entities/{entity_id}/views",
    tags=["ui-views"],
)
pages_router = APIRouter(
    prefix="/apps/{app_id}/pages",
    tags=["ui-pages"],
)


async def _check_app(app_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> None:
    try:
        await AppService(db).get_app(app_id, actor_id=current_user.user_id)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found") from exc


# ==================================================================
# Views
# ==================================================================


@views_router.get("", response_model=list[ViewRead])
async def list_views(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
    view_type: str | None = Query(default=None),
) -> list[ViewRead]:
    await _check_app(app_id, current_user, db)
    return await UIService(db).list_views(app_id, entity_id=entity_id, view_type=view_type)


@views_router.post("", response_model=ViewRead, status_code=status.HTTP_201_CREATED)
async def create_view(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    body: ViewCreate,
    current_user: AuthDep,
    db: DbDep,
) -> ViewRead:
    await _check_app(app_id, current_user, db)
    return await UIService(db).create_view(app_id, entity_id, body, creator_id=current_user.user_id)


@views_router.get("/{view_id}", response_model=ViewRead)
async def get_view(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    view_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> ViewRead:
    await _check_app(app_id, current_user, db)
    try:
        return await UIService(db).get_view(app_id, view_id)
    except ViewNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found") from exc


@views_router.patch("/{view_id}", response_model=ViewRead)
async def update_view(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    view_id: uuid.UUID,
    body: ViewUpdate,
    current_user: AuthDep,
    db: DbDep,
) -> ViewRead:
    await _check_app(app_id, current_user, db)
    try:
        return await UIService(db).update_view(app_id, view_id, body)
    except ViewNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found") from exc


@views_router.delete("/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_view(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    view_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> None:
    await _check_app(app_id, current_user, db)
    try:
        await UIService(db).delete_view(app_id, view_id)
    except ViewNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found") from exc


@views_router.post("/{view_id}/set_default", response_model=ViewRead)
async def set_default_view(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    view_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> ViewRead:
    """Make this view the default for its entity. Clears any prior default."""
    await _check_app(app_id, current_user, db)
    try:
        return await UIService(db).set_default_view(app_id, view_id)
    except ViewNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found") from exc


# ------------------------------------------------------------------
# View field configs
# ------------------------------------------------------------------


@views_router.get("/{view_id}/fields", response_model=list[ViewFieldConfigRead])
async def list_field_configs(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    view_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> list[ViewFieldConfigRead]:
    await _check_app(app_id, current_user, db)
    try:
        await UIService(db).get_view(app_id, view_id)
    except ViewNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found") from exc
    return await UIService(db).list_field_configs(view_id)


@views_router.put("/{view_id}/fields", response_model=list[ViewFieldConfigRead])
async def replace_field_configs(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    view_id: uuid.UUID,
    body: ViewFieldConfigBulkUpdate,
    current_user: AuthDep,
    db: DbDep,
) -> list[ViewFieldConfigRead]:
    """Full replacement of all field display configs for this view."""
    await _check_app(app_id, current_user, db)
    try:
        return await UIService(db).replace_field_configs(app_id, view_id, body)
    except ViewNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found") from exc


# ==================================================================
# Pages
# ==================================================================


@pages_router.put("/nav-order", response_model=list[PageRead])
async def reorder_pages(
    app_id: uuid.UUID,
    body: PageNavReorder,
    current_user: AuthDep,
    db: DbDep,
) -> list[PageRead]:
    """Bulk-update nav_order for pages in one app."""
    await _check_app(app_id, current_user, db)
    return await UIService(db).reorder_pages(app_id, body)


@pages_router.get("", response_model=list[PageRead])
async def list_pages(
    app_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> list[PageRead]:
    await _check_app(app_id, current_user, db)
    return await UIService(db).list_pages(app_id)


@pages_router.post("", response_model=PageRead, status_code=status.HTTP_201_CREATED)
async def create_page(
    app_id: uuid.UUID,
    body: PageCreate,
    current_user: AuthDep,
    db: DbDep,
) -> PageRead:
    await _check_app(app_id, current_user, db)
    try:
        return await UIService(db).create_page(app_id, body)
    except PageSlugConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "Page slug already exists", "slug": body.slug},
        ) from exc
    except BlockConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": exc.message, "field": exc.field, "reason": exc.reason},
        ) from exc


@pages_router.get("/{page_id}", response_model=PageRead)
async def get_page(
    app_id: uuid.UUID,
    page_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> PageRead:
    await _check_app(app_id, current_user, db)
    try:
        return await UIService(db).get_page(app_id, page_id)
    except PageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found") from exc


@pages_router.patch("/{page_id}", response_model=PageRead)
async def update_page(
    app_id: uuid.UUID,
    page_id: uuid.UUID,
    body: PageUpdate,
    current_user: AuthDep,
    db: DbDep,
) -> PageRead:
    await _check_app(app_id, current_user, db)
    try:
        return await UIService(db).update_page(app_id, page_id, body)
    except PageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found") from exc
    except BlockConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": exc.message, "field": exc.field, "reason": exc.reason},
        ) from exc


@pages_router.delete("/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_page(
    app_id: uuid.UUID,
    page_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> None:
    await _check_app(app_id, current_user, db)
    try:
        await UIService(db).delete_page(app_id, page_id)
    except PageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found") from exc


@pages_router.get("/{page_id}/permissions", response_model=list[PageRolePermissionRead])
async def get_page_permissions(
    app_id: uuid.UUID,
    page_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> list[PageRolePermissionRead]:
    await _check_app(app_id, current_user, db)
    try:
        await UIService(db).get_page(app_id, page_id)
    except PageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found") from exc
    return await UIService(db).get_page_permissions(page_id)


@pages_router.put("/{page_id}/permissions", response_model=list[PageRolePermissionRead])
async def set_page_permissions(
    app_id: uuid.UUID,
    page_id: uuid.UUID,
    body: PagePermissionsSet,
    current_user: AuthDep,
    db: DbDep,
) -> list[PageRolePermissionRead]:
    await _check_app(app_id, current_user, db)
    try:
        await UIService(db).get_page(app_id, page_id)
    except PageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found") from exc
    return await UIService(db).set_page_permissions(page_id, body)


@pages_router.post("/{page_id}/publish", response_model=PageRead)
async def publish_page(
    app_id: uuid.UUID,
    page_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> PageRead:
    await _check_app(app_id, current_user, db)
    try:
        return await UIService(db).publish_page(app_id, page_id)
    except PageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found") from exc


@pages_router.post("/{page_id}/unpublish", response_model=PageRead)
async def unpublish_page(
    app_id: uuid.UUID,
    page_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> PageRead:
    await _check_app(app_id, current_user, db)
    try:
        return await UIService(db).unpublish_page(app_id, page_id)
    except PageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found") from exc
