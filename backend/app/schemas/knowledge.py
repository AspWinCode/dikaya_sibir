"""Knowledge base schemas (ТЗ 3.12)."""
import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    base = _SLUG_RE.sub("-", title.lower()).strip("-") or "article"
    return f"{base}-{uuid.uuid4().hex[:6]}"


class ArticleRead(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    category: str | None
    display_order: int
    content: str
    is_published: bool
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ArticleListItem(BaseModel):
    """Lighter shape for list/search results — excerpt instead of full content."""
    id: uuid.UUID
    slug: str
    title: str
    category: str | None
    display_order: int
    excerpt: str
    is_published: bool
    updated_at: datetime
    model_config = {"from_attributes": True}


class ArticleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    slug: str | None = Field(default=None, min_length=1, max_length=200, pattern=r"^[a-z0-9][a-z0-9-]*$")
    category: str | None = Field(default=None, max_length=128)
    display_order: int = 0
    content: str = Field(default="", max_length=200_000)
    is_published: bool = True


class ArticleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=256)
    category: str | None = Field(default=None, max_length=128)
    display_order: int | None = None
    content: str | None = Field(default=None, max_length=200_000)
    is_published: bool | None = None


class ImageUploadResponse(BaseModel):
    id: uuid.UUID
    url: str
