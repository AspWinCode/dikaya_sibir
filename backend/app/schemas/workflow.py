"""Workflow Engine Pydantic schemas."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ------------------------------------------------------------------
# WorkflowDef
# ------------------------------------------------------------------


class WorkflowDefRead(BaseModel):
    id: uuid.UUID
    app_id: uuid.UUID
    entity_id: uuid.UUID
    name: str
    description: str | None
    initial_state: str
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class WorkflowDefCreate(BaseModel):
    entity_id: uuid.UUID
    name: str = Field(min_length=2, max_length=256)
    description: str | None = None
    initial_state: str = Field(min_length=1, max_length=128)


class WorkflowDefUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=256)
    description: str | None = None
    initial_state: str | None = Field(default=None, min_length=1, max_length=128)


# ------------------------------------------------------------------
# StateDef
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# ApprovalChain
# ------------------------------------------------------------------


class ApprovalLevelDefRead(BaseModel):
    id: uuid.UUID
    chain_id: uuid.UUID
    level_order: int
    display_name: str
    assignee_type: str | None
    assignee_id: str | None
    model_config = {"from_attributes": True}


class ApprovalLevelDefCreate(BaseModel):
    level_order: int = Field(ge=1)
    display_name: str = Field(min_length=1, max_length=256)
    assignee_type: str | None = None
    assignee_id: str | None = None


class ApprovalChainDefRead(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    name: str
    description: str | None
    on_approve_transition: str | None
    on_reject_transition: str | None
    levels: list[ApprovalLevelDefRead] = Field(default_factory=list)
    created_at: datetime
    model_config = {"from_attributes": True}


class ApprovalChainDefCreate(BaseModel):
    name: str = Field(min_length=2, max_length=256)
    description: str | None = None
    on_approve_transition: str | None = None
    on_reject_transition: str | None = None
    levels: list[ApprovalLevelDefCreate] = Field(default_factory=list)


class ApprovalChainDefUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=256)
    description: str | None = None
    on_approve_transition: str | None = None
    on_reject_transition: str | None = None
    levels: list[ApprovalLevelDefCreate] | None = None


class ApprovalChainInstanceRead(BaseModel):
    id: uuid.UUID
    chain_def_id: uuid.UUID
    workflow_instance_id: uuid.UUID
    current_level: int
    status: str
    started_at: datetime
    completed_at: datetime | None
    responses: list["ApprovalLevelResponseRead"] = Field(default_factory=list)
    model_config = {"from_attributes": True}


class ApprovalLevelResponseRead(BaseModel):
    id: uuid.UUID
    chain_instance_id: uuid.UUID
    level_order: int
    actor_id: uuid.UUID | None
    decision: str
    comment: str | None
    decided_at: datetime
    model_config = {"from_attributes": True}


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    comment: str | None = None


ApprovalChainInstanceRead.model_rebuild()


# ------------------------------------------------------------------
# StateDef
# ------------------------------------------------------------------


class StateDefRead(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    name: str
    display_name: str
    is_terminal: bool
    sla_seconds: int | None
    on_enter_actions: list[dict[str, Any]]
    on_exit_actions: list[dict[str, Any]]
    sla_breach_actions: list[dict[str, Any]]
    escalation_levels: list[dict[str, Any]]
    color: str | None
    assignee_type: str | None
    assignee_id: str | None
    approval_chain_id: uuid.UUID | None
    model_config = {"from_attributes": True}


class StateDefCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9_]+$",
        description="Machine name: lowercase, digits, underscores",
    )
    display_name: str = Field(min_length=1, max_length=256)
    is_terminal: bool = False
    sla_seconds: int | None = Field(default=None, ge=1)
    on_enter_actions: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    on_exit_actions: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    sla_breach_actions: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    escalation_levels: list[dict[str, Any]] = Field(default_factory=list, max_length=2)
    color: str | None = None
    assignee_type: str | None = None
    assignee_id: str | None = None
    approval_chain_id: uuid.UUID | None = None


class StateDefUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=256)
    is_terminal: bool | None = None
    sla_seconds: int | None = Field(default=None, ge=1)
    on_enter_actions: list[dict[str, Any]] | None = None
    on_exit_actions: list[dict[str, Any]] | None = None
    sla_breach_actions: list[dict[str, Any]] | None = None
    escalation_levels: list[dict[str, Any]] | None = None
    color: str | None = None
    assignee_type: str | None = None
    assignee_id: str | None = None
    approval_chain_id: uuid.UUID | None = None


# ------------------------------------------------------------------
# TransitionDef
# ------------------------------------------------------------------


class TransitionDefRead(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    name: str
    display_name: str
    from_state: str
    to_state: str
    guard_conditions: dict[str, Any]
    actions: list[dict[str, Any]]
    required_roles: list[str]
    display_order: int
    model_config = {"from_attributes": True}


class TransitionDefCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9_]+$")
    display_name: str = Field(min_length=1, max_length=256)
    from_state: str = Field(min_length=1, max_length=128)
    to_state: str = Field(min_length=1, max_length=128)
    guard_conditions: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    required_roles: list[str] = Field(default_factory=list)


class TransitionDefUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=256)
    from_state: str | None = Field(default=None, min_length=1, max_length=128)
    to_state: str | None = Field(default=None, min_length=1, max_length=128)
    guard_conditions: dict[str, Any] | None = None
    actions: list[dict[str, Any]] | None = None
    required_roles: list[str] | None = None
    display_order: int | None = None


# ------------------------------------------------------------------
# WorkflowInstance
# ------------------------------------------------------------------


class WorkflowInstanceRead(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    app_id: uuid.UUID
    entity_id: uuid.UUID
    record_id: uuid.UUID
    current_state: str
    version: int
    sla_deadline: datetime | None
    started_at: datetime
    completed_at: datetime | None
    assigned_user_id: uuid.UUID | None
    assigned_group_id: uuid.UUID | None
    escalation_level: int | None
    model_config = {"from_attributes": True}


class AssignInstanceRequest(BaseModel):
    assigned_user_id: uuid.UUID | None = None
    assigned_group_id: uuid.UUID | None = None


class StartInstanceRequest(BaseModel):
    record_id: uuid.UUID
    record_payload: dict[str, Any] = Field(default_factory=dict)


# ------------------------------------------------------------------
# Transition execution
# ------------------------------------------------------------------


class TransitionRequest(BaseModel):
    """Execute a named transition on a workflow instance."""

    transition_name: str = Field(min_length=1, max_length=128)
    record_payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Current record payload used to evaluate guard conditions and actions",
    )


class TransitionResponse(BaseModel):
    instance: WorkflowInstanceRead
    field_mutations: dict[str, Any]
    notifications: list[dict[str, Any]]
    webhooks: list[dict[str, Any]]
    errors: list[str]


# ------------------------------------------------------------------
# TransitionLog
# ------------------------------------------------------------------


class TransitionLogRead(BaseModel):
    id: uuid.UUID
    instance_id: uuid.UUID
    from_state: str | None
    to_state: str
    transition_id: uuid.UUID | None
    actor_id: uuid.UUID | None
    executed_at: datetime
    duration_ms: int | None
    error: str | None
    model_config = {"from_attributes": True}


# ------------------------------------------------------------------
# Available transitions response
# ------------------------------------------------------------------


class AvailableTransitionRead(BaseModel):
    name: str
    display_name: str
    to_state: str
    requires_roles: list[str]
