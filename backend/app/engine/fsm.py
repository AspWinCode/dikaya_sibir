"""
Workflow FSM evaluator.

Pure logic — no DB access, no Celery, no I/O.
The service layer is responsible for persisting results.

A workflow is a Finite State Machine where:
  - States can have on_enter / on_exit / sla_breach action lists (same JSON-AST as rules)
  - Transitions can have guard_conditions (same AST) and required_roles
  - Race condition protection is via conditional UPDATE in the service layer

Usage:
    spec = build_fsm_spec(wf_def_row, state_rows, transition_rows)
    result = execute_fsm_transition(spec, current_state="draft",
                                    transition_name="submit", ...)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.engine.interpreter import (
    ExecutionContext,
    ExecutionResult,
    evaluate_conditions,
    execute_actions,
)


class FSMError(Exception):
    pass


class TransitionNotFoundError(FSMError):
    def __init__(self, from_state: str, name: str) -> None:
        super().__init__(f"No transition '{name}' from state '{from_state}'")
        self.from_state = from_state
        self.name = name


class GuardNotMetError(FSMError):
    pass


class InsufficientRolesError(FSMError):
    def __init__(self, required: list[str]) -> None:
        super().__init__(f"Transition requires one of roles: {required}")
        self.required_roles = required


class TerminalStateError(FSMError):
    def __init__(self, state: str) -> None:
        super().__init__(f"Cannot transition from terminal state '{state}'")


# ------------------------------------------------------------------
# Spec data structures (converted from DB rows before evaluation)
# ------------------------------------------------------------------


@dataclass
class StateSpec:
    name: str
    display_name: str
    is_terminal: bool
    sla_seconds: int | None
    on_enter_actions: list[dict[str, Any]]
    on_exit_actions: list[dict[str, Any]]
    sla_breach_actions: list[dict[str, Any]]
    escalation_levels: list[dict[str, Any]]


@dataclass
class TransitionSpec:
    id: str
    name: str
    display_name: str
    from_state: str
    to_state: str
    guard_conditions: dict[str, Any]
    actions: list[dict[str, Any]]
    required_roles: list[str]


@dataclass
class FSMSpec:
    workflow_id: str
    initial_state: str
    states: dict[str, StateSpec]  # state name → StateSpec
    transitions: list[TransitionSpec]

    def get_state(self, name: str) -> StateSpec | None:
        return self.states.get(name)

    def get_transitions_from(self, from_state: str) -> list[TransitionSpec]:
        return [t for t in self.transitions if t.from_state == from_state]

    def find_transition(self, from_state: str, name: str) -> TransitionSpec | None:
        for t in self.transitions:
            if t.from_state == from_state and t.name == name:
                return t
        return None


# ------------------------------------------------------------------
# Builder: converts DB model rows → FSMSpec
# ------------------------------------------------------------------


def build_fsm_spec(
    workflow_def: Any,
    state_rows: list[Any],
    transition_rows: list[Any],
) -> FSMSpec:
    """Convert ORM objects into a pure FSMSpec for evaluation."""
    states = {
        s.name: StateSpec(
            name=s.name,
            display_name=s.display_name,
            is_terminal=s.is_terminal,
            sla_seconds=s.sla_seconds,
            on_enter_actions=list(s.on_enter_actions or []),
            on_exit_actions=list(s.on_exit_actions or []),
            sla_breach_actions=list(s.sla_breach_actions or []),
            escalation_levels=list(s.escalation_levels or []),
        )
        for s in state_rows
    }
    transitions = [
        TransitionSpec(
            id=str(t.id),
            name=t.name,
            display_name=t.display_name,
            from_state=t.from_state,
            to_state=t.to_state,
            guard_conditions=dict(t.guard_conditions or {}),
            actions=list(t.actions or []),
            required_roles=list(t.required_roles or []),
        )
        for t in transition_rows
    ]
    return FSMSpec(
        workflow_id=str(workflow_def.id),
        initial_state=workflow_def.initial_state,
        states=states,
        transitions=transitions,
    )


# ------------------------------------------------------------------
# Transition result
# ------------------------------------------------------------------


@dataclass
class FSMTransitionResult:
    new_state: str
    field_mutations: dict[str, Any] = field(default_factory=dict)
    records_to_create: list[dict[str, Any]] = field(default_factory=list)
    records_to_update: list[dict[str, Any]] = field(default_factory=list)
    records_to_delete: list[str] = field(default_factory=list)
    notifications: list[dict[str, Any]] = field(default_factory=list)
    webhooks: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    sla_seconds: int | None = None


# ------------------------------------------------------------------
# Core evaluator
# ------------------------------------------------------------------


def execute_fsm_transition(
    spec: FSMSpec,
    current_state: str,
    transition_name: str,
    record: dict[str, Any],
    entity_id: uuid.UUID,
    app_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    actor_roles: list[str] | None = None,
) -> FSMTransitionResult:
    """
    Evaluate a workflow transition. Pure — returns mutations only.

    Execution order:
      1. Validate transition exists + state is not terminal
      2. Check required_roles
      3. Evaluate guard_conditions
      4. Run on_exit_actions for current state
      5. Run transition.actions
      6. Run on_enter_actions for new state
      7. Return combined FSMTransitionResult
    """
    actor_roles = actor_roles or []

    # 1. Validate
    current_state_spec = spec.get_state(current_state)
    if current_state_spec and current_state_spec.is_terminal:
        raise TerminalStateError(current_state)

    transition = spec.find_transition(current_state, transition_name)
    if transition is None:
        raise TransitionNotFoundError(current_state, transition_name)

    # 2. Role check
    if transition.required_roles and not any(r in actor_roles for r in transition.required_roles):
        raise InsufficientRolesError(transition.required_roles)

    # 3. Guard conditions
    ctx = ExecutionContext(
        record=dict(record),
        entity_id=entity_id,
        app_id=app_id,
        event="workflow.transition",
        actor_id=actor_id,
    )
    if transition.guard_conditions and not evaluate_conditions(transition.guard_conditions, ctx):
        raise GuardNotMetError(f"Guard conditions for transition '{transition_name}' not met")

    result = FSMTransitionResult(new_state=transition.to_state)

    # 4. on_exit_actions for current state
    if current_state_spec and current_state_spec.on_exit_actions:
        _merge_actions(current_state_spec.on_exit_actions, ctx, result)

    # 5. transition.actions
    if transition.actions:
        _merge_actions(transition.actions, ctx, result)

    # 6. on_enter_actions for new state
    new_state_spec = spec.get_state(transition.to_state)
    if new_state_spec and new_state_spec.on_enter_actions:
        _merge_actions(new_state_spec.on_enter_actions, ctx, result)

    # 7. SLA for new state
    if new_state_spec:
        result.sla_seconds = new_state_spec.sla_seconds

    return result


def _merge_actions(
    actions: list[dict[str, Any]],
    ctx: ExecutionContext,
    result: FSMTransitionResult,
) -> None:
    """Execute action list and merge mutations into result."""
    exec_result: ExecutionResult = execute_actions(actions, ctx)
    result.field_mutations.update(exec_result.field_mutations)
    result.records_to_create.extend(exec_result.records_to_create)
    result.records_to_update.extend(exec_result.records_to_update)
    result.records_to_delete.extend(exec_result.records_to_delete)
    result.notifications.extend(exec_result.notifications)
    result.webhooks.extend(exec_result.webhooks)
    result.errors.extend(exec_result.errors)


# ------------------------------------------------------------------
# Start helper (initial state entry)
# ------------------------------------------------------------------


def enter_initial_state(
    spec: FSMSpec,
    record: dict[str, Any],
    entity_id: uuid.UUID,
    app_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
) -> FSMTransitionResult:
    """Run on_enter_actions for the initial state and return result."""
    result = FSMTransitionResult(new_state=spec.initial_state)
    state_spec = spec.get_state(spec.initial_state)
    if state_spec and state_spec.on_enter_actions:
        ctx = ExecutionContext(
            record=dict(record),
            entity_id=entity_id,
            app_id=app_id,
            event="workflow.started",
            actor_id=actor_id,
        )
        _merge_actions(state_spec.on_enter_actions, ctx, result)
    if state_spec:
        result.sla_seconds = state_spec.sla_seconds
    return result
