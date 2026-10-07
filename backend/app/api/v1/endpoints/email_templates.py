import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import DbDep
from app.schemas.email_templates import (
    EmailTemplateCreate,
    EmailTemplatePreviewRequest,
    EmailTemplatePreviewResponse,
    EmailTemplateRead,
    EmailTemplateUpdate,
)
from app.services.email_templates import (
    EmailTemplateConflictError,
    EmailTemplateNotFoundError,
    EmailTemplateRenderError,
    EmailTemplateService,
)

router = APIRouter(prefix="/email-templates", tags=["email-templates"])


def _svc(db: DbDep) -> EmailTemplateService:
    return EmailTemplateService(db)


@router.get("", response_model=list[EmailTemplateRead])
async def list_email_templates(
    svc: EmailTemplateService = Depends(_svc),
) -> list[EmailTemplateRead]:
    return await svc.list_templates()


@router.post("", response_model=EmailTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_email_template(
    body: EmailTemplateCreate, svc: EmailTemplateService = Depends(_svc)
) -> EmailTemplateRead:
    try:
        return await svc.create_template(body)
    except EmailTemplateConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{template_id}", response_model=EmailTemplateRead)
async def get_email_template(
    template_id: uuid.UUID, svc: EmailTemplateService = Depends(_svc)
) -> EmailTemplateRead:
    try:
        return await svc.get_template(template_id)
    except EmailTemplateNotFoundError:
        raise HTTPException(status_code=404, detail="Email template not found") from None


@router.patch("/{template_id}", response_model=EmailTemplateRead)
async def update_email_template(
    template_id: uuid.UUID,
    body: EmailTemplateUpdate,
    svc: EmailTemplateService = Depends(_svc),
) -> EmailTemplateRead:
    try:
        return await svc.update_template(template_id, body)
    except EmailTemplateNotFoundError:
        raise HTTPException(status_code=404, detail="Email template not found") from None


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_email_template(
    template_id: uuid.UUID, svc: EmailTemplateService = Depends(_svc)
) -> None:
    try:
        await svc.delete_template(template_id)
    except EmailTemplateNotFoundError:
        raise HTTPException(status_code=404, detail="Email template not found") from None
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/{template_id}/preview", response_model=EmailTemplatePreviewResponse)
async def preview_email_template(
    template_id: uuid.UUID,
    body: EmailTemplatePreviewRequest,
    svc: EmailTemplateService = Depends(_svc),
) -> EmailTemplatePreviewResponse:
    try:
        return await svc.render_template(template_id, body.context)
    except EmailTemplateNotFoundError:
        raise HTTPException(status_code=404, detail="Email template not found") from None
    except EmailTemplateRenderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
