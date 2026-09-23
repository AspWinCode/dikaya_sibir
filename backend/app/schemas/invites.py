import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class InviteLinkCreate(BaseModel):
    role: str = Field(default="editor", pattern=r"^(admin|editor|viewer)$")
    # None → link never expires
    expires_in_days: int | None = Field(default=7, ge=1, le=365)
    max_uses: int | None = Field(default=None, ge=1, le=10000)
    allow_signup: bool = True


class InviteLinkRead(BaseModel):
    id: uuid.UUID
    app_id: uuid.UUID
    role: str
    allow_signup: bool
    max_uses: int | None
    use_count: int
    expires_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


class InviteLinkCreated(InviteLinkRead):
    # Raw token — returned only once, at creation time
    token: str


class InvitePreview(BaseModel):
    app_id: uuid.UUID
    app_name: str
    role: str
    allow_signup: bool
    expires_at: datetime | None


class InviteAcceptResult(BaseModel):
    app_id: uuid.UUID
    role: str
    already_member: bool = False


class InviteSignupRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=256)
    password: str = Field(min_length=8, max_length=128)
