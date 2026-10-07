"""Template install endpoint — scaffold entities + pages from a built-in template."""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.deps import AuthDep, DbDep
from app.services.apps import AppNotFoundError, AppService
from app.services.templates import TemplateNotFoundError, TemplateService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/apps/{app_id}/templates", tags=["templates"])


class TemplateMeta(BaseModel):
    id: str
    name: str
    description: str | None = None
    modules: list[str] = []


class InstallResult(BaseModel):
    modules_installed: list[str] = []
    entities_created: int
    fields_created: int = 0
    pages_created: int


async def _check_app(app_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> None:
    try:
        await AppService(db).get_app(app_id, actor_id=current_user.user_id)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found") from exc


@router.get("", response_model=list[TemplateMeta])
async def list_templates(
    app_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> list[TemplateMeta]:
    """List available built-in templates."""
    await _check_app(app_id, current_user, db)
    svc = TemplateService(db)
    return [TemplateMeta(**svc.get_template_meta(tid)) for tid in svc.list_template_ids()]


@router.post(
    "/{template_id}/install", response_model=InstallResult, status_code=status.HTTP_201_CREATED
)
async def install_template(
    app_id: uuid.UUID,
    template_id: str,
    current_user: AuthDep,
    db: DbDep,
) -> InstallResult:
    """
    Scaffold entities (fields) and pages into the app from a built-in template.

    Idempotent in the sense that calling it twice will create duplicate entities
    (the slug uniqueness constraint will then raise 409). The caller should install
    a template only once per app.
    """
    await _check_app(app_id, current_user, db)
    try:
        result = await TemplateService(db).install(
            app_id=app_id,
            template_id=template_id,
            actor_id=current_user.user_id,
        )
    except TemplateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_id}' not found",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Install failed (possibly already installed): {exc}",
        ) from exc
    return InstallResult(**result)
