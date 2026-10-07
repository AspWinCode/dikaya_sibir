import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AuthDep, DbDep
from app.schemas.groups import GroupCreate, GroupDetailRead, GroupRead, GroupUpdate
from app.services.audit import AuditService
from app.services.groups import GroupConflictError, GroupNotFoundError, GroupService

router = APIRouter(prefix="/groups", tags=["groups"])


def _require_admin(current_user: AuthDep) -> None:
    if not current_user.has_role("platform_admin", "org_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )


@router.get("", response_model=list[GroupRead], summary="List all groups")
async def list_groups(current_user: AuthDep, db: DbDep) -> list[GroupRead]:
    if not current_user.has_role("platform_admin", "org_admin", "auditor"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    return await GroupService(db).list_groups()


@router.post(
    "", response_model=GroupDetailRead, status_code=status.HTTP_201_CREATED, summary="Create group"
)
async def create_group(body: GroupCreate, current_user: AuthDep, db: DbDep) -> GroupDetailRead:
    _require_admin(current_user)
    try:
        result = await GroupService(db).create_group(body)
        await AuditService(db).log(
            "group_created",
            user_id=current_user.user_id,
            actor_email=getattr(current_user, "email", None),
            resource_type="group",
            resource_id=str(result.id),
            level="info",
            details={"name": result.name, "roles": [r.id for r in result.roles]},
        )
        return result
    except GroupConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/{group_id}", response_model=GroupDetailRead, summary="Get group details")
async def get_group(group_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> GroupDetailRead:
    if not current_user.has_role("platform_admin", "org_admin", "auditor"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    try:
        return await GroupService(db).get_group(group_id)
    except GroupNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Group not found"
        ) from exc


@router.patch("/{group_id}", response_model=GroupDetailRead, summary="Update group")
async def update_group(
    group_id: uuid.UUID, body: GroupUpdate, current_user: AuthDep, db: DbDep
) -> GroupDetailRead:
    _require_admin(current_user)
    try:
        result = await GroupService(db).update_group(group_id, body)
        changed: dict = {}
        if body.name is not None:
            changed["name"] = body.name
        if body.description is not None:
            changed["description"] = body.description
        if body.role_ids is not None:
            changed["roles"] = body.role_ids
        await AuditService(db).log(
            "group_updated",
            user_id=current_user.user_id,
            actor_email=getattr(current_user, "email", None),
            resource_type="group",
            resource_id=str(group_id),
            level="info",
            details=changed,
        )
        return result
    except GroupNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Group not found"
        ) from exc
    except GroupConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete group")
async def delete_group(group_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> None:
    _require_admin(current_user)
    try:
        # Capture name before deletion
        detail = await GroupService(db).get_group(group_id)
        await GroupService(db).delete_group(group_id)
        await AuditService(db).log(
            "group_deleted",
            user_id=current_user.user_id,
            actor_email=getattr(current_user, "email", None),
            resource_type="group",
            resource_id=str(group_id),
            level="warn",
            details={"name": detail.name},
        )
    except GroupNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Group not found"
        ) from exc


@router.post(
    "/{group_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Add member to group",
)
async def add_member(
    group_id: uuid.UUID, user_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> None:
    _require_admin(current_user)
    try:
        await GroupService(db).add_member(group_id, user_id)
        await AuditService(db).log(
            "group_member_added",
            user_id=current_user.user_id,
            actor_email=getattr(current_user, "email", None),
            resource_type="group",
            resource_id=str(group_id),
            level="info",
            details={"member_user_id": str(user_id)},
        )
    except GroupNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Group not found"
        ) from exc


@router.delete(
    "/{group_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove member from group",
)
async def remove_member(
    group_id: uuid.UUID, user_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> None:
    _require_admin(current_user)
    try:
        await GroupService(db).remove_member(group_id, user_id)
        await AuditService(db).log(
            "group_member_removed",
            user_id=current_user.user_id,
            actor_email=getattr(current_user, "email", None),
            resource_type="group",
            resource_id=str(group_id),
            level="info",
            details={"member_user_id": str(user_id)},
        )
    except GroupNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Group not found"
        ) from exc


@router.post(
    "/{group_id}/apply-roles",
    summary="Grant group roles to all current members",
    response_model=dict,
)
async def apply_roles(group_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> dict:
    _require_admin(current_user)
    try:
        count = await GroupService(db).apply_roles_to_members(
            group_id, granted_by=current_user.user_id
        )
        await AuditService(db).log(
            "group_roles_applied",
            user_id=current_user.user_id,
            actor_email=getattr(current_user, "email", None),
            resource_type="group",
            resource_id=str(group_id),
            level="warn",
            details={"grants_added": count},
        )
        return {"grants_added": count}
    except GroupNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Group not found"
        ) from exc
