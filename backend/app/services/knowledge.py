"""KnowledgeService: article CRUD, search, and image hosting (ТЗ 3.12)."""

from __future__ import annotations

import re
import uuid
from html import unescape
from typing import ClassVar

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.antivirus import ClamAVClient
from app.core.config import settings
from app.core.storage import S3Storage
from app.models.knowledge import Article, ArticleImage
from app.schemas.knowledge import (
    ArticleCreate,
    ArticleListItem,
    ArticleRead,
    ArticleUpdate,
    ImageUploadResponse,
    slugify,
)

_TAG_RE = re.compile(r"<[^>]+>")
_EXCERPT_LEN = 200


class ArticleNotFoundError(Exception):
    pass


class ArticleSlugConflictError(Exception):
    pass


class ImageNotFoundError(Exception):
    pass


class ImageError(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def _excerpt(html_content: str) -> str:
    text = unescape(_TAG_RE.sub(" ", html_content))
    text = " ".join(text.split())
    return text[:_EXCERPT_LEN] + ("…" if len(text) > _EXCERPT_LEN else "")


class KnowledgeService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Articles
    # ------------------------------------------------------------------

    async def list_articles(
        self,
        category: str | None = None,
        query: str | None = None,
        include_unpublished: bool = False,
        limit: int = 50,
    ) -> list[ArticleListItem]:
        stmt = (
            select(Article)
            .order_by(Article.display_order.asc(), Article.updated_at.desc())
            .limit(limit)
        )
        if not include_unpublished:
            stmt = stmt.where(Article.is_published.is_(True))
        if category:
            stmt = stmt.where(Article.category == category)
        if query:
            like = f"%{query}%"
            stmt = stmt.where(or_(Article.title.ilike(like), Article.content.ilike(like)))

        rows = (await self._db.execute(stmt)).scalars().all()
        return [
            ArticleListItem(
                id=a.id,
                slug=a.slug,
                title=a.title,
                category=a.category,
                display_order=a.display_order,
                excerpt=_excerpt(a.content),
                is_published=a.is_published,
                updated_at=a.updated_at,
            )
            for a in rows
        ]

    async def list_categories(self) -> list[str]:
        rows = (
            (
                await self._db.execute(
                    select(Article.category)
                    .where(
                        Article.is_published.is_(True),
                        Article.category.is_not(None),
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        return sorted(c for c in rows if c)

    async def get_article(self, id_or_slug: str, include_unpublished: bool = False) -> ArticleRead:
        article = await self._fetch(id_or_slug)
        if not article.is_published and not include_unpublished:
            raise ArticleNotFoundError(id_or_slug)
        return ArticleRead.model_validate(article)

    async def create_article(self, data: ArticleCreate, actor_id: uuid.UUID | None) -> ArticleRead:
        slug = data.slug or slugify(data.title)
        article = Article(
            slug=slug,
            title=data.title,
            category=data.category,
            display_order=data.display_order,
            content=data.content,
            is_published=data.is_published,
            created_by=actor_id,
        )
        self._db.add(article)
        try:
            await self._db.flush()
        except IntegrityError as exc:
            raise ArticleSlugConflictError(slug) from exc
        return ArticleRead.model_validate(article)

    async def update_article(self, id_or_slug: str, data: ArticleUpdate) -> ArticleRead:
        article = await self._fetch(id_or_slug)
        if data.title is not None:
            article.title = data.title
        if data.category is not None:
            article.category = data.category
        if data.display_order is not None:
            article.display_order = data.display_order
        if data.content is not None:
            article.content = data.content
        if data.is_published is not None:
            article.is_published = data.is_published
        await self._db.flush()
        await self._db.refresh(article, attribute_names=["updated_at"])
        return ArticleRead.model_validate(article)

    async def delete_article(self, id_or_slug: str) -> None:
        article = await self._fetch(id_or_slug)
        await self._db.delete(article)
        await self._db.flush()

    async def _fetch(self, id_or_slug: str) -> Article:
        try:
            article_id = uuid.UUID(id_or_slug)
            stmt = select(Article).where(Article.id == article_id)
        except ValueError:
            stmt = select(Article).where(Article.slug == id_or_slug)
        article = (await self._db.execute(stmt)).scalar_one_or_none()
        if article is None:
            raise ArticleNotFoundError(id_or_slug)
        return article

    # ------------------------------------------------------------------
    # Images
    # ------------------------------------------------------------------

    _ALLOWED_IMAGE_TYPES: ClassVar[set[str]] = {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "image/svg+xml",
    }
    _MAX_IMAGE_SIZE: ClassVar[int] = 10 * 1024 * 1024  # 10 MB

    async def upload_image(
        self,
        data: bytes,
        content_type: str,
        storage: S3Storage,
        av: ClamAVClient,
        actor_id: uuid.UUID | None,
        article_id: uuid.UUID | None = None,
    ) -> ImageUploadResponse:
        if content_type not in self._ALLOWED_IMAGE_TYPES:
            raise ImageError(f"Unsupported image type: {content_type!r}")
        if len(data) > self._MAX_IMAGE_SIZE:
            raise ImageError(
                f"Image exceeds the maximum size of {self._MAX_IMAGE_SIZE // 1_048_576} MB"
            )

        is_clean, verdict = await av.scan_bytes(data)
        if not is_clean:
            raise ImageError("Image failed antivirus scan", status_code=422)

        ext = content_type.split("/")[-1].replace("svg+xml", "svg")
        s3_key = f"kb/{uuid.uuid4()}.{ext}"
        await storage.upload(settings.S3_BUCKET_FILES, s3_key, data, content_type=content_type)

        image = ArticleImage(
            article_id=article_id,
            s3_key=s3_key,
            content_type=content_type,
            created_by=actor_id,
        )
        self._db.add(image)
        await self._db.flush()
        return ImageUploadResponse(id=image.id, url=f"/api/v1/kb/images/{image.id}/file")

    async def get_image_url(self, image_id: uuid.UUID, storage: S3Storage) -> str:
        result = await self._db.execute(select(ArticleImage).where(ArticleImage.id == image_id))
        image = result.scalar_one_or_none()
        if image is None:
            raise ImageNotFoundError(str(image_id))
        return await storage.get_presigned_url(settings.S3_BUCKET_FILES, image.s3_key, expires=3600)
