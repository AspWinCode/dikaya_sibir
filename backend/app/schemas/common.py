from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class CursorPage(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False
    total: int | None = None


class ErrorDetail(BaseModel):
    loc: list[str | int] | None = None
    msg: str
    type: str


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    errors: list[ErrorDetail] | None = None


class HealthStatus(BaseModel):
    status: str
    version: str
    checks: dict[str, Any] = Field(default_factory=dict)
