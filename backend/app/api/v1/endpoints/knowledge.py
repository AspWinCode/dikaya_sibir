import uuid

import structlog
from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import RedirectResponse

from app.api.deps import AuthDep, DbDep
from app.core.antivirus import get_antivirus
from app.core.rate_limit import limiter
from app.core.storage import get_storage
from app.schemas.knowledge import (
    ArticleCreate,
    ArticleListItem,
    ArticleRead,
    ArticleUpdate,
    ImageUploadResponse,
)
from app.services.knowledge import (
    ArticleNotFoundError,
    ArticleSlugConflictError,
    ImageError,
    ImageNotFoundError,
    KnowledgeService,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/kb", tags=["knowledge-base"])


def _require_admin(current_user: AuthDep) -> None:
    if not current_user.has_role("platform_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a platform admin can manage knowledge base content",
        )


@router.get("/articles", response_model=list[ArticleListItem])
async def list_articles(
    current_user: AuthDep,
    db: DbDep,
    category: str | None = Query(default=None),
    q: str | None = Query(default=None, description="Search title and content"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ArticleListItem]:
    include_unpublished = current_user.has_role("platform_admin")
    return await KnowledgeService(db).list_articles(
        category=category,
        query=q,
        include_unpublished=include_unpublished,
        limit=limit,
    )


@router.get("/categories", response_model=list[str])
async def list_categories(current_user: AuthDep, db: DbDep) -> list[str]:
    return await KnowledgeService(db).list_categories()


@router.get("/articles/{id_or_slug}", response_model=ArticleRead)
async def get_article(id_or_slug: str, current_user: AuthDep, db: DbDep) -> ArticleRead:
    try:
        return await KnowledgeService(db).get_article(
            id_or_slug,
            include_unpublished=current_user.has_role("platform_admin"),
        )
    except ArticleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Article not found"
        ) from exc


@router.post("/articles", response_model=ArticleRead, status_code=status.HTTP_201_CREATED)
async def create_article(body: ArticleCreate, current_user: AuthDep, db: DbDep) -> ArticleRead:
    _require_admin(current_user)
    try:
        return await KnowledgeService(db).create_article(body, actor_id=current_user.user_id)
    except ArticleSlugConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"Slug {exc} already in use"
        ) from exc


@router.patch("/articles/{id_or_slug}", response_model=ArticleRead)
async def update_article(
    id_or_slug: str, body: ArticleUpdate, current_user: AuthDep, db: DbDep
) -> ArticleRead:
    _require_admin(current_user)
    try:
        return await KnowledgeService(db).update_article(id_or_slug, body)
    except ArticleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Article not found"
        ) from exc


@router.delete("/articles/{id_or_slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_article(id_or_slug: str, current_user: AuthDep, db: DbDep) -> None:
    _require_admin(current_user)
    try:
        await KnowledgeService(db).delete_article(id_or_slug)
    except ArticleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Article not found"
        ) from exc


@router.post("/images", response_model=ImageUploadResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def upload_image(
    file: UploadFile,
    request: Request,
    current_user: AuthDep,
    db: DbDep,
    article_id: uuid.UUID | None = Query(default=None),
) -> ImageUploadResponse:
    _require_admin(current_user)
    data = await file.read()
    try:
        return await KnowledgeService(db).upload_image(
            data,
            file.content_type or "application/octet-stream",
            get_storage(),
            get_antivirus(),
            actor_id=current_user.user_id,
            article_id=article_id,
        )
    except ImageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/images/{image_id}/file")
async def get_image_file(image_id: uuid.UUID, db: DbDep) -> RedirectResponse:
    """Stable URL to embed in article content — always redirects to a fresh
    presigned S3 URL, so it never goes stale even though the presigned URL
    itself expires.

    Deliberately unauthenticated: this is rendered as a plain <img src=...>
    in article HTML, and browsers don't attach the app's Authorization
    header to those requests. Only decorative help-article images are
    reachable this way — never user/business data — so that's an acceptable
    trade for a working <img> tag.
    """
    try:
        url = await KnowledgeService(db).get_image_url(image_id, get_storage())
    except ImageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Image not found"
        ) from exc
    return RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
