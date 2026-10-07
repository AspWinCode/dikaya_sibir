"""Integration layer schemas — webhook subscriptions and delivery history."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ------------------------------------------------------------------
# WebhookSubscription
# ------------------------------------------------------------------


class WebhookSubscriptionRead(BaseModel):
    id: uuid.UUID
    app_id: uuid.UUID
    name: str
    target_url: str
    events: list[str]
    is_active: bool
    custom_headers: dict[str, str]
    timeout_seconds: int
    max_retries: int
    created_at: datetime
    updated_at: datetime
    # secret intentionally excluded from read responses
    model_config = {"from_attributes": True}


class WebhookSubscriptionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    target_url: str = Field(min_length=8, max_length=2048)
    events: list[str] = Field(
        default=["*"],
        min_length=1,
        max_length=20,
        description='Event patterns: ["*"], ["record.*"], ["record.created"]',
    )
    custom_headers: dict[str, str] = Field(default_factory=dict, max_length=20)
    timeout_seconds: int = Field(default=30, ge=5, le=120)
    max_retries: int = Field(default=3, ge=0, le=10)

    @field_validator("target_url")
    @classmethod
    def url_must_be_https_or_http(cls, v: str) -> str:
        if not (v.startswith("https://") or v.startswith("http://")):
            raise ValueError("target_url must start with http:// or https://")
        return v

    @field_validator("events")
    @classmethod
    def validate_event_patterns(cls, v: list[str]) -> list[str]:
        for pattern in v:
            if not pattern or len(pattern) > 128:
                raise ValueError(f"Invalid event pattern: {pattern!r}")
        return v


class WebhookSubscriptionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    target_url: str | None = Field(default=None, min_length=8, max_length=2048)
    events: list[str] | None = Field(default=None, min_length=1, max_length=20)
    is_active: bool | None = None
    custom_headers: dict[str, str] | None = None
    timeout_seconds: int | None = Field(default=None, ge=5, le=120)
    max_retries: int | None = Field(default=None, ge=0, le=10)


class RotateSecretResponse(BaseModel):
    """New secret returned only once on rotation — store it immediately."""

    id: uuid.UUID
    secret: str


# ------------------------------------------------------------------
# WebhookDelivery
# ------------------------------------------------------------------


class WebhookDeliveryRead(BaseModel):
    id: uuid.UUID
    subscription_id: uuid.UUID
    event_type: str
    status: str
    attempt_count: int
    last_response_code: int | None
    last_response_body: str | None
    error: str | None
    created_at: datetime
    delivered_at: datetime | None
    model_config = {"from_attributes": True}


# ------------------------------------------------------------------
# Outbox (internal — used by OutboxWriter, not exposed via API)
# ------------------------------------------------------------------


class OutboxPublish(BaseModel):
    """Payload for writing an event to the transactional outbox."""

    event_type: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any]
    dedup_key: str | None = None
