import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AppMemberRead(BaseModel):
    user_id: uuid.UUID
    role: str
    granted_at: datetime
    email: str | None = None
    display_name: str | None = None
    model_config = {"from_attributes": True}


class AppRead(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    icon: str | None
    color: str | None
    category: str | None = None
    owner_id: uuid.UUID
    org_id: uuid.UUID | None = None
    is_published: bool
    is_archived: bool
    settings: dict
    version: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class AppCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=128, pattern=r"^[a-z0-9][a-z0-9\-_]*$")
    name: str = Field(min_length=2, max_length=256)
    description: str | None = None
    icon: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, max_length=32)
    category: str | None = Field(default=None, max_length=64)
    settings: dict = Field(default_factory=dict)


class AppUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=256)
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    category: str | None = None
    settings: dict | None = None


class AppMemberAdd(BaseModel):
    user_id: uuid.UUID
    role: str = Field(pattern=r"^(owner|admin|editor|viewer)$")


class LockInfo(BaseModel):
    user_id: str
    holder_name: str
    acquired_at: datetime


class AppCloneCreate(BaseModel):
    name: str = Field(min_length=2, max_length=256)
    slug: str | None = Field(
        default=None,
        min_length=2,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9\-_]*$",
    )


class AppSnapshotRead(BaseModel):
    id: uuid.UUID
    app_id: uuid.UUID
    snapshot_num: int
    created_by: uuid.UUID | None
    comment: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class AppSnapshotCreate(BaseModel):
    comment: str | None = Field(default=None, max_length=512)


class PublishIssue(BaseModel):
    """One integrity-check finding (ТЗ 3.11.1). `severity="error"` blocks
    publication; `"warning"` is informational only. `location` carries enough
    ids for the UI to link straight to the problem element."""

    severity: str = Field(pattern=r"^(error|warning)$")
    category: str  # "block_no_source" | "rule_empty" | "workflow_transition" | "relation_invalid"
    message: str
    location: dict[str, str] = Field(default_factory=dict)


class PublishCheckResult(BaseModel):
    can_publish: bool
    issues: list[PublishIssue] = Field(default_factory=list)
