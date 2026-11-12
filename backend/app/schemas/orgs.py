import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class OrgCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=128, pattern=r"^[a-z0-9_-]+$")
    display_name: str = Field(min_length=2, max_length=256)
    plan: str = Field(default="trial", max_length=64)
    admin_email: str = Field(
        description="Email первого org_admin",
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        max_length=256,
    )
    admin_display_name: str = Field(min_length=2, max_length=256)
    admin_password: str = Field(min_length=10, max_length=128)


class OrgUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=256)
    plan: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None


class OrgRead(BaseModel):
    id: uuid.UUID
    slug: str
    display_name: str
    plan: str
    is_active: bool
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
