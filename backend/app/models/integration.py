"""
ORM models for the integration schema.

integration.outbox       — created in 0003_data_records; model defined here.
integration.webhook_subscription — created in 0007_integration.
integration.webhook_delivery     — created in 0007_integration.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Outbox(Base):
    """
    Transactional outbox table.  Written within the same DB transaction as
    the triggering mutation; polled by the beat task every 10 s.
    """

    __tablename__ = "outbox"
    __table_args__ = {"schema": "integration"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Caller-supplied idempotency key; unique only while status = 'pending'
    dedup_key: Mapped[str | None] = mapped_column(sa.String(256))
    # pending → processing → processed | failed
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default="'pending'")
    scheduled_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    processed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscription"
    __table_args__ = {"schema": "integration"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    target_url: Mapped[str] = mapped_column(sa.String(2048), nullable=False)
    events: Mapped[list] = mapped_column(JSONB, nullable=False, server_default='["*"]')
    secret: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default="true")
    custom_headers: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    timeout_seconds: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="30")
    max_retries: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="3")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


class WebhookDelivery(Base):
    __tablename__ = "webhook_delivery"
    __table_args__ = {"schema": "integration"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("integration.webhook_subscription.id", ondelete="CASCADE"),
        nullable=False,
    )
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    outbox_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default="'pending'")
    attempt_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    next_retry_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    last_response_code: Mapped[int | None] = mapped_column(sa.Integer)
    last_response_body: Mapped[str | None] = mapped_column(sa.String(4096))
    error: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    delivered_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
