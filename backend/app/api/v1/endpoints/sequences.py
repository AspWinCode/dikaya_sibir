"""Document registrar / auto-number sequence endpoints."""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import AuthDep, DbDep
from app.services.apps import AppNotFoundError, AppService
from app.services.sequences import (
    SequenceAlreadyExistsError,
    SequenceNotFoundError,
    SequenceService,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/apps/{app_id}/entities/{entity_id}/sequences",
    tags=["sequences"],
)


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class SequenceRead(BaseModel):
    id: uuid.UUID
    app_id: uuid.UUID
    entity_id: uuid.UUID
    field_name: str
    prefix: str
    suffix: str
    padding: int
    step: int
    next_value: int
    reset_on: str | None

    model_config = {"from_attributes": True}


class SequenceCreate(BaseModel):
    field_name: str = Field(..., min_length=1, max_length=128)
    prefix: str = Field(default="", max_length=32)
    suffix: str = Field(default="", max_length=32)
    padding: int = Field(default=0, ge=0, le=20)
    step: int = Field(default=1, ge=1, le=1000)
    start: int = Field(default=1, ge=1)
    reset_on: str | None = Field(default=None)


class SequenceUpdate(BaseModel):
    prefix: str | None = Field(default=None, max_length=32)
    suffix: str | None = Field(default=None, max_length=32)
    padding: int | None = Field(default=None, ge=0, le=20)
    step: int | None = Field(default=None, ge=1, le=1000)
    reset_on: str | None = None


class NextValueResponse(BaseModel):
    value: str


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


async def _check_app(app_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> None:
    try:
        await AppService(db).get_app(app_id, actor_id=current_user.user_id)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found") from exc


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("", response_model=list[SequenceRead])
async def list_sequences(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> list[SequenceRead]:
    await _check_app(app_id, current_user, db)
    seqs = await SequenceService(db).list_sequences(app_id, entity_id)
    return [SequenceRead.model_validate(s) for s in seqs]


@router.post("", response_model=SequenceRead, status_code=status.HTTP_201_CREATED)
async def create_sequence(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    body: SequenceCreate,
    current_user: AuthDep,
    db: DbDep,
) -> SequenceRead:
    await _check_app(app_id, current_user, db)
    try:
        seq = await SequenceService(db).create_sequence(
            app_id=app_id,
            entity_id=entity_id,
            field_name=body.field_name,
            prefix=body.prefix,
            suffix=body.suffix,
            padding=body.padding,
            step=body.step,
            start=body.start,
            reset_on=body.reset_on,
        )
    except SequenceAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return SequenceRead.model_validate(seq)


@router.get("/{sequence_id}", response_model=SequenceRead)
async def get_sequence(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    sequence_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> SequenceRead:
    await _check_app(app_id, current_user, db)
    try:
        seq = await SequenceService(db).get_sequence(app_id, entity_id, sequence_id)
    except SequenceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sequence not found"
        ) from exc
    return SequenceRead.model_validate(seq)


@router.patch("/{sequence_id}", response_model=SequenceRead)
async def update_sequence(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    sequence_id: uuid.UUID,
    body: SequenceUpdate,
    current_user: AuthDep,
    db: DbDep,
) -> SequenceRead:
    await _check_app(app_id, current_user, db)
    try:
        seq = await SequenceService(db).update_sequence(
            app_id,
            entity_id,
            sequence_id,
            prefix=body.prefix,
            suffix=body.suffix,
            padding=body.padding,
            step=body.step,
            reset_on=body.reset_on,
        )
    except SequenceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sequence not found"
        ) from exc
    return SequenceRead.model_validate(seq)


@router.delete("/{sequence_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_sequence(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    sequence_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> Response:
    await _check_app(app_id, current_user, db)
    try:
        await SequenceService(db).delete_sequence(app_id, entity_id, sequence_id)
    except SequenceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sequence not found"
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{sequence_id}/next", response_model=NextValueResponse)
async def get_next_value(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    sequence_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> NextValueResponse:
    """Preview the next sequence value without consuming it (for UI display)."""
    await _check_app(app_id, current_user, db)
    try:
        seq = await SequenceService(db).get_sequence(app_id, entity_id, sequence_id)
    except SequenceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sequence not found"
        ) from exc
    numeric = str(seq.next_value).zfill(seq.padding) if seq.padding > 0 else str(seq.next_value)
    return NextValueResponse(value=f"{seq.prefix}{numeric}{seq.suffix}")
