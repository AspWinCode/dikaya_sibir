import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WorkflowDef(Base):
    __tablename__ = "workflow_def"
    __table_args__ = {"schema": "workflow"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text)
    initial_state: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default="false")
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


class StateDef(Base):
    __tablename__ = "state_def"
    __table_args__ = (
        sa.UniqueConstraint("workflow_id", "name", name="uq_state_def_wf_name"),
        {"schema": "workflow"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("workflow.workflow_def.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    is_terminal: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default="false")
    sla_seconds: Mapped[int | None] = mapped_column(sa.Integer)
    on_enter_actions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    on_exit_actions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    sla_breach_actions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    escalation_levels: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    color: Mapped[str | None] = mapped_column(sa.String(32))
    assignee_type: Mapped[str | None] = mapped_column(sa.String(16))
    assignee_id: Mapped[str | None] = mapped_column(sa.String(128))
    approval_chain_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("workflow.approval_chain_def.id", ondelete="SET NULL"),
    )


class TransitionDef(Base):
    __tablename__ = "transition_def"
    __table_args__ = (
        sa.UniqueConstraint(
            "workflow_id", "from_state", "name", name="uq_transition_def_wf_from_name"
        ),
        {"schema": "workflow"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("workflow.workflow_def.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    from_state: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    to_state: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    guard_conditions: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    actions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    required_roles: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    display_order: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")


class WorkflowInstance(Base):
    __tablename__ = "workflow_instance"
    __table_args__ = (
        sa.UniqueConstraint("workflow_id", "record_id", name="uq_instance_wf_record"),
        {"schema": "workflow"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("workflow.workflow_def.id"),
        nullable=False,
    )
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    current_state: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="1")
    sla_deadline: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    assigned_group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    escalation_level: Mapped[int | None] = mapped_column(sa.Integer)


class ApprovalChainDef(Base):
    __tablename__ = "approval_chain_def"
    __table_args__ = {"schema": "workflow"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("workflow.workflow_def.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text)
    on_approve_transition: Mapped[str | None] = mapped_column(sa.String(128))
    on_reject_transition: Mapped[str | None] = mapped_column(sa.String(128))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


class ApprovalLevelDef(Base):
    __tablename__ = "approval_level_def"
    __table_args__ = (
        sa.UniqueConstraint("chain_id", "level_order", name="uq_approval_level_chain_order"),
        {"schema": "workflow"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    chain_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("workflow.approval_chain_def.id", ondelete="CASCADE"),
        nullable=False,
    )
    level_order: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    assignee_type: Mapped[str | None] = mapped_column(sa.String(16))
    assignee_id: Mapped[str | None] = mapped_column(sa.String(128))


class ApprovalChainInstance(Base):
    __tablename__ = "approval_chain_instance"
    __table_args__ = {"schema": "workflow"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    chain_def_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workflow_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("workflow.workflow_instance.id", ondelete="CASCADE"),
        nullable=False,
    )
    current_level: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default="'pending'")
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class ApprovalLevelResponse(Base):
    __tablename__ = "approval_level_response"
    __table_args__ = {"schema": "workflow"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    chain_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("workflow.approval_chain_instance.id", ondelete="CASCADE"),
        nullable=False,
    )
    level_order: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decision: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(sa.Text)
    decided_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


class TransitionLog(Base):
    __tablename__ = "transition_log"
    __table_args__ = {"schema": "workflow"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("workflow.workflow_instance.id", ondelete="CASCADE"),
        nullable=False,
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    from_state: Mapped[str | None] = mapped_column(sa.String(128))
    to_state: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    transition_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    executed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer)
    error: Mapped[str | None] = mapped_column(sa.Text)
