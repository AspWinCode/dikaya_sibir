"""UI Builder schemas — views, field configs, pages."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# ------------------------------------------------------------------
# View types + config envelopes
# ------------------------------------------------------------------


class ViewType(str, Enum):
    TABLE = "table"
    FORM = "form"
    KANBAN = "kanban"
    CALENDAR = "calendar"
    GALLERY = "gallery"
    DETAIL = "detail"


class TableConfig(BaseModel):
    """Column order, row height, frozen columns, default sort/filter."""

    columns: list[str] = Field(default_factory=list)
    sort: list[dict[str, Any]] = Field(default_factory=list)
    filters: list[dict[str, Any]] = Field(default_factory=list)
    row_height: Literal["compact", "default", "tall"] = "default"
    frozen_columns: int = Field(default=0, ge=0)


class KanbanConfig(BaseModel):
    group_by_field: str
    card_fields: list[str] = Field(default_factory=list)
    column_order: list[str] = Field(default_factory=list)
    card_cover_field: str | None = None


class CalendarConfig(BaseModel):
    date_field: str
    end_date_field: str | None = None
    title_field: str
    color_field: str | None = None


class FormConfig(BaseModel):
    sections: list[dict[str, Any]] = Field(default_factory=list)
    submit_label: str = "Save"
    success_message: str = "Saved successfully"
    redirect_page_id: uuid.UUID | None = None


# ------------------------------------------------------------------
# View
# ------------------------------------------------------------------


class ViewRead(BaseModel):
    id: uuid.UUID
    app_id: uuid.UUID
    entity_id: uuid.UUID
    name: str
    view_type: str
    config: dict[str, Any]
    is_default: bool
    is_public: bool
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ViewCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    view_type: ViewType
    config: dict[str, Any] = Field(default_factory=dict)
    is_public: bool = True


class ViewUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    config: dict[str, Any] | None = None
    is_public: bool | None = None


# ------------------------------------------------------------------
# ViewFieldConfig
# ------------------------------------------------------------------


class WidgetType(str, Enum):
    DEFAULT = "default"
    TEXT = "text"
    RICH_TEXT = "rich_text"
    NUMBER = "number"
    CHECKBOX = "checkbox"
    DATE_PICKER = "date_picker"
    SELECT = "select"
    FILE_UPLOAD = "file_upload"
    IMAGE = "image"
    RELATION = "relation"
    FORMULA = "formula"


class ViewFieldConfigItem(BaseModel):
    field_name: str = Field(min_length=1, max_length=128)
    is_visible: bool = True
    is_readonly: bool = False
    display_order: int = Field(default=0, ge=0)
    width: int | None = Field(default=None, ge=20, le=2000)
    widget_type: str | None = None
    widget_config: dict[str, Any] = Field(default_factory=dict)


class ViewFieldConfigRead(ViewFieldConfigItem):
    id: uuid.UUID
    view_id: uuid.UUID
    model_config = {"from_attributes": True}


class ViewFieldConfigBulkUpdate(BaseModel):
    """Full replacement of all field configs for a view."""

    fields: list[ViewFieldConfigItem] = Field(max_length=200)

    @field_validator("fields")
    @classmethod
    def unique_field_names(cls, v: list[ViewFieldConfigItem]) -> list[ViewFieldConfigItem]:
        names = [f.field_name for f in v]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate field_name entries")
        return v


# ------------------------------------------------------------------
# Page blocks
# ------------------------------------------------------------------


class BlockType(str, Enum):
    # Input
    TEXT_FIELD = "text_field"
    NUMBER_FIELD = "number_field"
    DATE_FIELD = "date_field"
    DROPDOWN = "dropdown"
    TOGGLE = "toggle"
    CHECKBOX = "checkbox"
    FILE_UPLOAD = "file_upload"
    LOOKUP = "lookup"
    FORM = "form"
    POSITIONS_PICKER = "positions_picker"
    # Display
    TABLE = "table"
    RECORD_CARD = "record_card"
    METRIC = "metric"
    KPI = "kpi"
    CHART = "chart"
    PIVOT = "pivot"
    CALENDAR = "calendar"
    KANBAN = "kanban"
    GANTT = "gantt"
    TREE = "tree"
    RICH_TEXT = "rich_text"
    VIEW = "view"
    # Action
    BUTTON = "button"
    IMPORT = "import"
    EXPORT = "export"
    # Container
    MODAL = "modal"
    TABS = "tabs"
    FILTER_PANEL = "filter_panel"
    DIVIDER = "divider"
    IFRAME = "iframe"


class PageBlock(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    type: BlockType
    title: str | None = None
    # view block
    view_id: uuid.UUID | None = None
    # rich_text block
    content: str | None = None
    # metric block / general config
    config: dict[str, Any] = Field(default_factory=dict)


# ------------------------------------------------------------------
# Page
# ------------------------------------------------------------------


class LayoutType(str, Enum):
    FULL_WIDTH = "full_width"
    SIDEBAR = "sidebar"
    TWO_COLUMN = "two_column"


class PageLayout(BaseModel):
    type: LayoutType = LayoutType.FULL_WIDTH
    sidebar_width: int = Field(default=240, ge=160, le=480)


class PageRead(BaseModel):
    id: uuid.UUID
    app_id: uuid.UUID
    slug: str
    title: str
    icon: str | None
    nav_order: int
    layout: dict[str, Any]
    blocks: list[dict[str, Any]]
    breakpoints: dict[str, Any]
    is_published: bool
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class PageCreate(BaseModel):
    slug: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9-]+$",
        description="URL slug: lowercase, digits, hyphens",
    )
    title: str = Field(min_length=1, max_length=256)
    icon: str | None = None
    nav_order: int = Field(default=0, ge=0)
    layout: dict[str, Any] = Field(default_factory=dict)
    blocks: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    breakpoints: dict[str, Any] = Field(default_factory=dict)


class PageUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=256)
    icon: str | None = None
    nav_order: int | None = Field(default=None, ge=0)
    layout: dict[str, Any] | None = None
    blocks: list[dict[str, Any]] | None = Field(default=None, max_length=50)
    breakpoints: dict[str, Any] | None = None


# ------------------------------------------------------------------
# Page role permissions
# ------------------------------------------------------------------


class PageRolePermissionRead(BaseModel):
    page_id: uuid.UUID
    role_id: str
    can_view: bool
    model_config = {"from_attributes": True}


class PageRolePermissionItem(BaseModel):
    role_id: str = Field(min_length=1, max_length=128)
    can_view: bool = True


class PagePermissionsSet(BaseModel):
    permissions: list[PageRolePermissionItem] = Field(default_factory=list)


# ------------------------------------------------------------------
# Nav reorder
# ------------------------------------------------------------------


class PageNavReorderItem(BaseModel):
    page_id: uuid.UUID
    nav_order: int = Field(ge=0)


class PageNavReorder(BaseModel):
    pages: list[PageNavReorderItem] = Field(min_length=1)
