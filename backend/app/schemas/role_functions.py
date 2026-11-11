"""Schemas for the per-role function checklist (see app.core.permissions)."""

from pydantic import BaseModel, Field


class FunctionCatalogItem(BaseModel):
    code: str
    label: str
    description: str
    group: str


class RoleFunctionsRead(BaseModel):
    role_id: str
    # platform_admin: every function, can't be edited.
    locked: bool
    is_system: bool
    # Function codes the role may use right now (defaults + overrides).
    allowed: list[str]
    # Function codes the role has out of the box (used for "reset to defaults").
    defaults: list[str]


class RoleFunctionsUpdate(BaseModel):
    allowed: list[str] = Field(default_factory=list, max_length=100)
