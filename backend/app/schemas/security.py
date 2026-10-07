"""Security schemas: field-level ABAC, resource permissions, ABAC rules."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FieldPermissionRead(BaseModel):
    id: uuid.UUID
    app_id: uuid.UUID
    entity_id: uuid.UUID
    field_name: str
    role_id: str
    can_read: bool
    can_write: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class FieldPermissionUpsert(BaseModel):
    """Create or replace a field permission for one (field_name, role_id) pair."""

    field_name: str = Field(min_length=1, max_length=128)
    role_id: str = Field(min_length=1, max_length=128)
    can_read: bool = True
    can_write: bool = True


class FieldPermissionBulkUpsert(BaseModel):
    """Full replacement of all field permissions for one entity."""

    permissions: list[FieldPermissionUpsert] = Field(max_length=500)


class FieldRestrictionsResponse(BaseModel):
    """Result of an ABAC check for a given caller + entity."""

    entity_id: uuid.UUID
    denied_read: list[str]  # field names the caller cannot read
    denied_write: list[str]  # field names the caller cannot write


# ── Resource permissions ────────────────────────────────────────────────────


class ResourcePermissionRead(BaseModel):
    id: uuid.UUID
    role_id: str
    resource_type: str
    resource_id: str
    action: str
    allowed: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class ResourcePermissionUpsert(BaseModel):
    """Create or replace a single resource permission."""

    role_id: str = Field(min_length=1, max_length=64)
    resource_type: str = Field(min_length=1, max_length=32)
    resource_id: str = Field(min_length=1, max_length=256)
    action: str = Field(min_length=1, max_length=32)
    allowed: bool = True


class ResourcePermissionBulkUpsert(BaseModel):
    """Full replacement of all permissions for a given role."""

    permissions: list[ResourcePermissionUpsert] = Field(max_length=1000)


# ── ABAC rules ──────────────────────────────────────────────────────────────


class AbacRuleRead(BaseModel):
    id: uuid.UUID
    role_id: str
    resource_type: str
    resource_id: str | None
    condition_json: list[Any]
    effect: str
    priority: int
    description: str | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class AbacRuleCreate(BaseModel):
    role_id: str = Field(min_length=1, max_length=64)
    resource_type: str = Field(min_length=1, max_length=128)
    resource_id: str | None = Field(default=None, max_length=256)
    condition_json: list[Any] = Field(default_factory=list)
    effect: str = Field(default="allow", pattern="^(allow|deny)$")
    priority: int = Field(default=0, ge=0, le=1000)
    description: str | None = Field(default=None, max_length=512)


class AbacRuleUpdate(BaseModel):
    resource_type: str | None = Field(default=None, min_length=1, max_length=128)
    resource_id: str | None = Field(default=None, max_length=256)
    condition_json: list[Any] | None = None
    effect: str | None = Field(default=None, pattern="^(allow|deny)$")
    priority: int | None = Field(default=None, ge=0, le=1000)
    description: str | None = Field(default=None, max_length=512)
