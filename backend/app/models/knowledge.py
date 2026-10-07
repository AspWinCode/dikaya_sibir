"""Knowledge base (ТЗ 3.12) — admin-authored help articles with search."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Article(Base):
    __tablename__ = "article"
    __table_args__ = {"schema": "support"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # Manual display order within a category (ascending). Admin-controlled —
    # see KnowledgeService.list_articles / the Learning page's materials+steps.
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # HTML — a rich-text/video-embed body (ТЗ 3.12: "текст, изображения, видео").
    # Images are embedded via <img src="/api/v1/kb/images/{id}/file">, which
    # always resolves to a fresh presigned S3 URL (see ArticleImage below).
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ArticleImage(Base):
    """An uploaded image, optionally linked to the article it was embedded
    into. `GET /kb/images/{id}/file` redirects to a freshly generated
    presigned URL each time, so URLs baked into `Article.content` never
    expire even though the underlying S3 presigned URL does."""

    __tablename__ = "article_image"
    __table_args__ = {"schema": "support"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("support.article.id", ondelete="SET NULL"), nullable=True
    )
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
