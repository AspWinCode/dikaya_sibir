import uuid

import structlog
from fastapi import APIRouter, HTTPException, status

from app.api.deps import AuthDep, DbDep
from app.schemas.orgs import OrgCreate, OrgRead, OrgUpdate
from app.services.orgs import OrgConflictError, OrgNotFoundError, OrgService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/orgs", tags=["organisations"])


def _require_platform_admin(current_user: AuthDep) -> None:
    if not current_user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )


@router.get("", response_model=list[OrgRead], summary="List all organisations")
async def list_orgs(current_user: AuthDep, db: DbDep) -> list[OrgRead]:
    _require_platform_admin(current_user)
    return await OrgService(db).list_orgs()


@router.post(
    "",
    response_model=OrgRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create organisation and its first org_admin",
)
async def create_org(body: OrgCreate, current_user: AuthDep, db: DbDep) -> OrgRead:
    _require_platform_admin(current_user)
    try:
        return await OrgService(db).create_org(
            body,
            created_by=current_user.user_id,
            actor_email=getattr(current_user, "email", None),
        )
    except OrgConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/{org_id}", response_model=OrgRead, summary="Get organisation by ID")
async def get_org(org_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> OrgRead:
    if not current_user.is_platform_admin and current_user.org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    try:
        return await OrgService(db).get_org(org_id)
    except OrgNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found"
        ) from exc


@router.patch("/{org_id}", response_model=OrgRead, summary="Update organisation")
async def update_org(
    org_id: uuid.UUID, body: OrgUpdate, current_user: AuthDep, db: DbDep
) -> OrgRead:
    _require_platform_admin(current_user)
    try:
        return await OrgService(db).update_org(
            org_id,
            body,
            updated_by=current_user.user_id,
            actor_email=getattr(current_user, "email", None),
        )
    except OrgNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found"
        ) from exc
