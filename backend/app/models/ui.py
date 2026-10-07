import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ViewType(str, enum.Enum):
    TABLE = "table"
    FORM = "form"
    KANBAN = "kanban"
    CALENDAR = "calendar"
    GALLERY = "gallery"
    DETAIL = "detail"


class View(Base):
    __tablename__ = "view"
    __table_args__ = {"schema": "ui"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    view_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    is_default: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default="false")
    is_public: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default="true")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


class ViewFieldConfig(Base):
    __tablename__ = "view_field_config"
    __table_args__ = (
        sa.UniqueConstraint("view_id", "field_name", name="uq_view_field_config"),
        {"schema": "ui"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    view_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("ui.view.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    is_visible: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default="true")
    is_readonly: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default="false")
    display_order: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    width: Mapped[int | None] = mapped_column(sa.Integer)
    widget_type: Mapped[str | None] = mapped_column(sa.String(64))
    widget_config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


class Page(Base):
    __tablename__ = "page"
    __table_args__ = (
        sa.UniqueConstraint("app_id", "slug", name="uq_ui_page_app_slug"),
        {"schema": "ui"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    slug: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    title: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    icon: Mapped[str | None] = mapped_column(sa.String(64))
    nav_order: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    layout: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    blocks: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    breakpoints: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    is_published: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default="false")
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


class PageRolePermission(Base):
    __tablename__ = "page_role_permission"
    __table_args__ = {"schema": "ui"}

    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("ui.page.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_id: Mapped[str] = mapped_column(sa.String(128), primary_key=True)
    can_view: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default="true")
