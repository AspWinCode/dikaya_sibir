"""
Field-level ABAC endpoints.

Admin API for managing which roles can read/write which fields.
Enforcement happens in records.py via ABACService.get_restrictions().
"""

import uuid

import structlog
from fastapi import APIRouter, HTTPException, status

from app.api.deps import AuthDep, DbDep
from app.schemas.security import (
    FieldPermissionBulkUpsert,
    FieldPermissionRead,
    FieldRestrictionsResponse,
)
from app.services.apps import AppNotFoundError, AppService
from app.services.security import ABACService

logger = structlog.get_logger(__name__)
router = APIRouter(
    prefix="/apps/{app_id}/entities/{entity_id}/permissions",
    tags=["security"],
)


async def _check_app(app_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> None:
    try:
        await AppService(db).get_app(app_id, actor_id=current_user.user_id)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found") from exc


@router.get("", response_model=list[FieldPermissionRead])
async def list_permissions(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> list[FieldPermissionRead]:
    """List all field-level permissions defined for this entity."""
    await _check_app(app_id, current_user, db)
    return await ABACService(db).list_permissions(app_id, entity_id)


@router.put("", response_model=list[FieldPermissionRead])
async def replace_permissions(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    body: FieldPermissionBulkUpsert,
    current_user: AuthDep,
    db: DbDep,
) -> list[FieldPermissionRead]:
    """
    Full replacement of all field permissions for this entity.

    Send an empty list to remove all restrictions (open access).
    Deny-wins semantics: a row with can_read=false blocks read for that role.
    """
    await _check_app(app_id, current_user, db)
    return await ABACService(db).bulk_upsert(app_id, entity_id, body)


@router.delete("/{perm_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_permission(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    perm_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> None:
    """Remove a single field permission row."""
    await _check_app(app_id, current_user, db)
    await ABACService(db).delete_permission(app_id, entity_id, perm_id)


@router.get("/check", response_model=FieldRestrictionsResponse)
async def check_my_permissions(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> FieldRestrictionsResponse:
    """
    Return field restrictions for the current caller.
    Useful for frontends that want to hide/disable restricted fields.
    """
    await _check_app(app_id, current_user, db)
    restrictions = await ABACService(db).get_restrictions(entity_id, current_user.roles)
    return restrictions.to_response()
