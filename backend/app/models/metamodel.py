import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class FieldType(str, Enum):
    TEXT = "text"
    LONG_TEXT = "long_text"
    RICH_TEXT = "rich_text"
    NUMBER = "number"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    TIME = "time"
    SELECT = "select"
    MULTI_SELECT = "multi_select"
    FILE = "file"
    IMAGE = "image"
    RELATION = "relation"
    FORMULA = "formula"
    CURRENCY = "currency"
    SIGNATURE = "signature"
    URL = "url"
    EMAIL = "email"
    PHONE = "phone"
    JSON = "json"
    LOOKUP = "lookup"
    AUTONUMBER = "autonumber"


class RelationType(str, Enum):
    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_MANY = "many_to_many"


class Entity(Base):
    __tablename__ = "entity"
    __table_args__ = (
        UniqueConstraint("app_id", "slug", name="uq_entity_app_slug"),
        {"schema": "metamodel"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("catalog.app.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    name_plural: Mapped[str | None] = mapped_column(String(256), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str | None] = mapped_column(String(64), nullable=True)
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Ordered list of field IDs — maintained by reorder endpoint
    field_order: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    app: Mapped["app.models.catalog.App"] = relationship("App", back_populates="entities")  # type: ignore[name-defined]
    fields: Mapped[list["Field"]] = relationship(
        "Field", back_populates="entity", cascade="all, delete-orphan", lazy="selectin"
    )
    outgoing_relations: Mapped[list["Relation"]] = relationship(
        "Relation",
        foreign_keys="[Relation.from_entity_id]",
        back_populates="from_entity",
        passive_deletes=True,
    )
    incoming_relations: Mapped[list["Relation"]] = relationship(
        "Relation",
        foreign_keys="[Relation.to_entity_id]",
        back_populates="to_entity",
        passive_deletes=True,
    )


class Field(Base):
    __tablename__ = "field"
    __table_args__ = (
        UniqueConstraint("entity_id", "name", name="uq_field_entity_name"),
        {"schema": "metamodel"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metamodel.entity.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Denormalized for index-only scans
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    field_type: Mapped[str] = mapped_column(String(64), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_unique: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_indexed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Validation rules: {"min": 0, "max": 100, "regex": "..."}
    validation_rules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Type-specific options: {"choices": [...]} for select, {"target_entity_id": "..."} for relation
    field_options: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # For formula fields: stores the expression AST + text representation
    formula_definition: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # AES-256-GCM encrypted at rest (app/core/field_crypto.py) and masked in
    # reads/exports unless the caller's role is explicitly granted read via
    # FieldPermission (ТЗ 3.13: шифрование + маскирование по полю).
    is_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    entity: Mapped["Entity"] = relationship("Entity", back_populates="fields")


class Relation(Base):
    __tablename__ = "relation"
    __table_args__ = {"schema": "metamodel"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    from_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metamodel.entity.id", ondelete="CASCADE"),
        nullable=False,
    )
    to_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metamodel.entity.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    from_field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    to_field_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    from_entity: Mapped["Entity"] = relationship(
        "Entity", foreign_keys=[from_entity_id], back_populates="outgoing_relations"
    )
    to_entity: Mapped["Entity"] = relationship(
        "Entity", foreign_keys=[to_entity_id], back_populates="incoming_relations"
    )
