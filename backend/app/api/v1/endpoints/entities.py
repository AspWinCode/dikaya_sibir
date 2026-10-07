import uuid

import structlog
from fastapi import APIRouter, HTTPException, status

from app.api.deps import AuthDep, DbDep
from app.schemas.entities import (
    EntityCreate,
    EntityRead,
    EntityUpdate,
    FieldCreate,
    FieldRead,
    FieldReorderRequest,
    FieldUpdate,
    RelationCreate,
    RelationRead,
    RelationUpdate,
)
from app.services.apps import AppNotFoundError, AppService
from app.services.entities import (
    EntityConflictError,
    EntityNotFoundError,
    EntityService,
    FieldConflictError,
    FieldNotFoundError,
    RelationConflictError,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/apps/{app_id}", tags=["entities"])


async def _check_app_access(
    app_id: uuid.UUID, current_user: AuthDep, db: DbDep, require_role: set[str] | None = None
) -> None:
    """Verify caller can access the app; optionally require specific member role."""
    try:
        await AppService(db).get_app(app_id, actor_id=current_user.user_id)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found") from exc


# ------------------------------------------------------------------
# Entities
# ------------------------------------------------------------------


@router.get("/entities", response_model=list[EntityRead])
async def list_entities(app_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> list[EntityRead]:
    await _check_app_access(app_id, current_user, db)
    return await EntityService(db).list_entities(app_id)


@router.post("/entities", response_model=EntityRead, status_code=status.HTTP_201_CREATED)
async def create_entity(
    app_id: uuid.UUID, body: EntityCreate, current_user: AuthDep, db: DbDep
) -> EntityRead:
    await _check_app_access(app_id, current_user, db)
    try:
        return await EntityService(db).create_entity(app_id, body)
    except EntityConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/entities/{entity_id}", response_model=EntityRead)
async def get_entity(
    app_id: uuid.UUID, entity_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> EntityRead:
    await _check_app_access(app_id, current_user, db)
    try:
        return await EntityService(db).get_entity(app_id, entity_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found"
        ) from exc


@router.patch("/entities/{entity_id}", response_model=EntityRead)
async def update_entity(
    app_id: uuid.UUID, entity_id: uuid.UUID, body: EntityUpdate, current_user: AuthDep, db: DbDep
) -> EntityRead:
    await _check_app_access(app_id, current_user, db)
    try:
        return await EntityService(db).update_entity(app_id, entity_id, body)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found"
        ) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.delete("/entities/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entity(
    app_id: uuid.UUID, entity_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> None:
    await _check_app_access(app_id, current_user, db)
    try:
        await EntityService(db).delete_entity(app_id, entity_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found"
        ) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


# ------------------------------------------------------------------
# Fields
# ------------------------------------------------------------------


@router.post(
    "/entities/{entity_id}/fields",
    response_model=FieldRead,
    status_code=status.HTTP_201_CREATED,
    tags=["fields"],
)
async def create_field(
    app_id: uuid.UUID, entity_id: uuid.UUID, body: FieldCreate, current_user: AuthDep, db: DbDep
) -> FieldRead:
    await _check_app_access(app_id, current_user, db)
    try:
        return await EntityService(db).create_field(app_id, entity_id, body)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found"
        ) from exc
    except FieldConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch(
    "/entities/{entity_id}/fields/{field_id}",
    response_model=FieldRead,
    tags=["fields"],
)
async def update_field(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    field_id: uuid.UUID,
    body: FieldUpdate,
    current_user: AuthDep,
    db: DbDep,
) -> FieldRead:
    await _check_app_access(app_id, current_user, db)
    try:
        return await EntityService(db).update_field(app_id, entity_id, field_id, body)
    except (EntityNotFoundError, FieldNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.delete(
    "/entities/{entity_id}/fields/{field_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["fields"],
)
async def delete_field(
    app_id: uuid.UUID, entity_id: uuid.UUID, field_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> None:
    await _check_app_access(app_id, current_user, db)
    try:
        await EntityService(db).delete_field(app_id, entity_id, field_id)
    except (EntityNotFoundError, FieldNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post(
    "/entities/{entity_id}/fields/reorder",
    response_model=EntityRead,
    tags=["fields"],
)
async def reorder_fields(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    body: FieldReorderRequest,
    current_user: AuthDep,
    db: DbDep,
) -> EntityRead:
    await _check_app_access(app_id, current_user, db)
    try:
        return await EntityService(db).reorder_fields(app_id, entity_id, body)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


# ------------------------------------------------------------------
# Relations
# ------------------------------------------------------------------


@router.get("/relations", response_model=list[RelationRead], tags=["relations"])
async def list_relations(app_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> list[RelationRead]:
    await _check_app_access(app_id, current_user, db)
    return await EntityService(db).list_relations(app_id)


@router.post(
    "/relations",
    response_model=RelationRead,
    status_code=status.HTTP_201_CREATED,
    tags=["relations"],
)
async def create_relation(
    app_id: uuid.UUID, body: RelationCreate, current_user: AuthDep, db: DbDep
) -> RelationRead:
    await _check_app_access(app_id, current_user, db)
    try:
        return await EntityService(db).create_relation(app_id, body)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found"
        ) from exc
    except RelationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch("/relations/{relation_id}", response_model=RelationRead, tags=["relations"])
async def update_relation(
    app_id: uuid.UUID,
    relation_id: uuid.UUID,
    body: RelationUpdate,
    current_user: AuthDep,
    db: DbDep,
) -> RelationRead:
    await _check_app_access(app_id, current_user, db)
    try:
        return await EntityService(db).update_relation(app_id, relation_id, body)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Relation not found"
        ) from exc
    except FieldConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete(
    "/relations/{relation_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["relations"]
)
async def delete_relation(
    app_id: uuid.UUID, relation_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> None:
    await _check_app_access(app_id, current_user, db)
    try:
        await EntityService(db).delete_relation(app_id, relation_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Relation not found"
        ) from exc
