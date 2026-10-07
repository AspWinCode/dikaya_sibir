import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Rule(Base):
    __tablename__ = "rule"
    __table_args__ = {"schema": "logic"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # {"event": "record.created|record.updated|record.deleted|field.changed|schedule",
    #  "watch_fields": [...], "schedule_kind": "cron|relative_date",
    #  "cron": {...}, "relative_date": {...}}
    trigger: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Root condition node — AST
    conditions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Array of action nodes — AST
    actions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # "automation" | "autofill"
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False, default="automation")
    # Lower number = runs first when multiple rules match
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RuleExecutionLog(Base):
    """Append-only execution log. Partitioned by month in migration."""

    __tablename__ = "rule_execution_log"
    __table_args__ = {"schema": "logic"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    # 'success' | 'failed' | 'skipped' | 'timeout'
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RuleConflictLog(Base):
    """Append-only log of field-level rule conflicts (ТЗ 3.5.4): two rules in
    the same batch tried to set the same field to different values. One row
    per (record, field, batch) — `losing_writes` lists every rule that lost,
    not just the first."""

    __tablename__ = "rule_conflict_log"
    __table_args__ = {"schema": "logic"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    winning_rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    winning_value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    # [{"rule_id": "...", "value": ...}, ...]
    losing_writes: Mapped[list] = mapped_column(JSONB, nullable=False)
    execution_batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RuleWebhookDelivery(Base):
    """Delivery attempts for `call_webhook` rule actions (ТЗ 3.5 rule actions).

    Separate from integration.webhook_delivery: that table is for
    admin-configured subscriptions to domain events; this one is for
    ad-hoc URLs authored directly inside a rule's actions."""

    __tablename__ = "rule_webhook_delivery"
    __table_args__ = {"schema": "logic"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    execution_batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    method: Mapped[str] = mapped_column(String(8), nullable=False, default="POST")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 'delivered' | 'failed' | 'blocked'
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
