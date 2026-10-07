"""
RBAC endpoints: custom role CRUD, resource permissions, ABAC rules.
All mutations require platform_admin.
"""

import uuid

import structlog
from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AuthDep, DbDep
from app.schemas.security import (
    AbacRuleCreate,
    AbacRuleRead,
    AbacRuleUpdate,
    ResourcePermissionBulkUpsert,
    ResourcePermissionRead,
)
from app.schemas.users import RoleCreate, RoleRead, RoleUpdate
from app.services.abac import AbacConditionError
from app.services.roles import (
    RoleNotFoundError,
    RolePermissionError,
    RoleService,
)

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["roles"])


def _require_platform_admin(current_user: AuthDep) -> None:
    if not current_user.has_role("platform_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only platform_admin")


# ── Role CRUD ───────────────────────────────────────────────────────────────


@router.get("/roles", response_model=list[RoleRead], summary="List all roles")
async def list_roles(current_user: AuthDep, db: DbDep) -> list[RoleRead]:
    if not current_user.has_role("platform_admin", "org_admin", "auditor"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    actor_org_id = None if current_user.has_role("platform_admin") else current_user.org_id
    return await RoleService(db).list_roles(actor_org_id=actor_org_id)


@router.post(
    "/roles",
    response_model=RoleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a custom role",
)
async def create_role(body: RoleCreate, current_user: AuthDep, db: DbDep) -> RoleRead:
    if not current_user.has_role("platform_admin", "org_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    org_id = None if current_user.has_role("platform_admin") else current_user.org_id
    return await RoleService(db).create_role(
        body,
        created_by=current_user.user_id,
        actor_email=getattr(current_user, "email", None),
        org_id=org_id,
    )


@router.patch("/roles/{role_id}", response_model=RoleRead, summary="Update a custom role")
async def update_role(role_id: str, body: RoleUpdate, current_user: AuthDep, db: DbDep) -> RoleRead:
    _require_platform_admin(current_user)
    try:
        return await RoleService(db).update_role(
            role_id,
            body,
            updated_by=current_user.user_id,
            actor_email=getattr(current_user, "email", None),
        )
    except RoleNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RolePermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.delete(
    "/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a custom (non-system) role",
)
async def delete_role(role_id: str, current_user: AuthDep, db: DbDep) -> None:
    if not current_user.has_role("platform_admin", "org_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    actor_org_id = None if current_user.has_role("platform_admin") else current_user.org_id
    try:
        await RoleService(db).delete_role(
            role_id,
            deleted_by=current_user.user_id,
            actor_email=getattr(current_user, "email", None),
            actor_org_id=actor_org_id,
        )
    except RoleNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RolePermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


# ── Resource permissions ────────────────────────────────────────────────────


@router.get(
    "/roles/{role_id}/permissions",
    response_model=list[ResourcePermissionRead],
    summary="List resource permissions for a role",
)
async def list_role_permissions(
    role_id: str, current_user: AuthDep, db: DbDep
) -> list[ResourcePermissionRead]:
    if not current_user.has_role("platform_admin", "org_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    return await RoleService(db).list_resource_permissions(role_id=role_id)


@router.put(
    "/roles/{role_id}/permissions",
    response_model=list[ResourcePermissionRead],
    summary="Replace all resource permissions for a role",
)
async def replace_role_permissions(
    role_id: str,
    body: ResourcePermissionBulkUpsert,
    current_user: AuthDep,
    db: DbDep,
) -> list[ResourcePermissionRead]:
    if not current_user.has_role("platform_admin", "org_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    svc = RoleService(db)
    if current_user.has_role("org_admin") and not current_user.has_role("platform_admin"):
        try:
            role = await svc._get_role(role_id)
        except RoleNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if role.org_id != current_user.org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify permissions for role from another organisation",
            )
    return await svc.bulk_upsert_resource_permissions(
        role_id,
        body,
        updated_by=current_user.user_id,
        actor_email=getattr(current_user, "email", None),
    )


# ── ABAC rules ──────────────────────────────────────────────────────────────


@router.get(
    "/abac-rules",
    response_model=list[AbacRuleRead],
    summary="List ABAC record-level rules",
)
async def list_abac_rules(
    current_user: AuthDep,
    db: DbDep,
    role_id: str | None = Query(default=None),
) -> list[AbacRuleRead]:
    if not current_user.has_role("platform_admin", "org_admin", "auditor"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    return await RoleService(db).list_abac_rules(role_id=role_id)


@router.post(
    "/abac-rules",
    response_model=AbacRuleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an ABAC rule",
)
async def create_abac_rule(
    body: AbacRuleCreate,
    current_user: AuthDep,
    db: DbDep,
) -> AbacRuleRead:
    _require_platform_admin(current_user)
    try:
        return await RoleService(db).create_abac_rule(
            body,
            created_by=current_user.user_id,
            actor_email=getattr(current_user, "email", None),
        )
    except AbacConditionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.patch(
    "/abac-rules/{rule_id}",
    response_model=AbacRuleRead,
    summary="Update an ABAC rule",
)
async def update_abac_rule(
    rule_id: uuid.UUID,
    body: AbacRuleUpdate,
    current_user: AuthDep,
    db: DbDep,
) -> AbacRuleRead:
    _require_platform_admin(current_user)
    try:
        return await RoleService(db).update_abac_rule(
            rule_id,
            body,
            updated_by=current_user.user_id,
            actor_email=getattr(current_user, "email", None),
        )
    except RoleNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AbacConditionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.delete(
    "/abac-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an ABAC rule",
)
async def delete_abac_rule(
    rule_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> None:
    _require_platform_admin(current_user)
    await RoleService(db).delete_abac_rule(
        rule_id,
        deleted_by=current_user.user_id,
        actor_email=getattr(current_user, "email", None),
    )
