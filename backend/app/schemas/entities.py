import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.metamodel import FieldType, RelationType


class FieldRead(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    app_id: uuid.UUID
    name: str
    display_name: str
    field_type: str
    is_required: bool
    is_unique: bool
    is_system: bool
    is_indexed: bool
    is_sensitive: bool = False
    default_value: Any | None
    validation_rules: dict
    field_options: dict
    formula_definition: dict | None = None
    display_order: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class FieldCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str = Field(min_length=1, max_length=256)
    field_type: FieldType
    is_required: bool = False
    is_unique: bool = False
    is_indexed: bool = False
    # AES-256-GCM encrypted at rest + masked by default (ТЗ 3.13). Not
    # exposed on FieldUpdate — flipping it after records exist would leave
    # a plaintext/ciphertext mismatch with no safe automatic re-encryption.
    is_sensitive: bool = False
    default_value: Any | None = None
    validation_rules: dict = Field(default_factory=dict)
    field_options: dict = Field(default_factory=dict)
    formula_definition: dict | None = None

    @model_validator(mode="after")
    def validate_sensitive_not_unique(self) -> "FieldCreate":
        # AES-GCM uses a random nonce per encryption, so two equal plaintexts
        # never produce equal ciphertext — a uniqueness check against the
        # stored value could never work for an encrypted field.
        if self.is_sensitive and self.is_unique:
            raise ValueError("A sensitive (encrypted) field cannot also be unique")
        return self


class FieldUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=256)
    is_required: bool | None = None
    is_unique: bool | None = None
    is_indexed: bool | None = None
    default_value: Any | None = None
    validation_rules: dict | None = None
    field_options: dict | None = None
    formula_definition: dict | None = None


class FieldReorderRequest(BaseModel):
    field_ids: list[uuid.UUID] = Field(min_length=1)


class EntityRead(BaseModel):
    id: uuid.UUID
    app_id: uuid.UUID
    slug: str
    display_name: str
    name_plural: str | None
    description: str | None
    icon: str | None
    color: str | None
    settings: dict
    is_system: bool
    field_order: list
    fields: list[FieldRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class EntityCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str = Field(min_length=2, max_length=256)
    name_plural: str | None = Field(default=None, max_length=256)
    description: str | None = None
    icon: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, max_length=32)
    settings: dict = Field(default_factory=dict)


class EntityUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=256)
    name_plural: str | None = None
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    settings: dict | None = None


class RelationRead(BaseModel):
    id: uuid.UUID
    app_id: uuid.UUID
    from_entity_id: uuid.UUID
    to_entity_id: uuid.UUID
    relation_type: str
    from_field_name: str
    to_field_name: str | None
    display_name: str | None
    settings: dict
    created_at: datetime
    model_config = {"from_attributes": True}


class RelationCreate(BaseModel):
    from_entity_id: uuid.UUID
    to_entity_id: uuid.UUID
    relation_type: RelationType
    from_field_name: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    to_field_name: str | None = Field(default=None, max_length=128)
    display_name: str | None = Field(default=None, max_length=256)
    settings: dict = Field(default_factory=dict)


class RelationUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=256)
    from_field_name: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$"
    )
    to_field_name: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$"
    )
