"""
Rules Engine interpreter.

Evaluates condition trees and executes action lists against a record payload.
No eval(), no exec(), no imports from user input.

Condition node schema:
  {"type": "and|or|not", "children": [...]}
  {"type": "compare", "field": "amount", "op": "gt", "value": expr_or_literal}

Action node schema:
  {"type": "set_field",          "field": "f",   "value": expr}
  {"type": "create_record",      "entity_id": "uuid", "payload": {field: expr}}
  {"type": "update_record",      "record_id_field": "id_field", "payload": {field: expr}}
  {"type": "delete_record",      "record_id_field": "id_field"}
  {"type": "send_notification",  "to_field": "email", "subject": str, "template": str}
  {"type": "call_webhook",       "url": str, "method": "POST", "payload": {field: expr}}
  {"type": "stop"}

ExecutionResult holds the mutations; actual DB writes happen in RuleService.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.engine.expressions import ExpressionError, evaluate

_MAX_ACTIONS = 20
_COMPARE_OPS = frozenset(
    {
        "eq",
        "ne",
        "gt",
        "gte",
        "lt",
        "lte",
        "contains",
        "icontains",
        "in",
        "nin",
        "is_null",
        "is_not_null",
        "starts_with",
        "ends_with",
    }
)


class RuleError(Exception):
    pass


@dataclass
class ExecutionContext:
    record: dict[str, Any]  # current record payload
    entity_id: uuid.UUID
    app_id: uuid.UUID
    event: str  # e.g. "record.updated"
    actor_id: uuid.UUID | None = None
    record_id: uuid.UUID | None = None  # ID of the triggering record
    changed_fields: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)  # injected at runtime


@dataclass
class ExecutionResult:
    matched: bool = False
    stopped: bool = False
    field_mutations: dict[str, Any] = field(default_factory=dict)
    records_to_create: list[dict[str, Any]] = field(default_factory=list)
    records_to_update: list[dict[str, Any]] = field(default_factory=list)
    records_to_delete: list[str] = field(default_factory=list)
    notifications: list[dict[str, Any]] = field(default_factory=list)
    webhooks: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ------------------------------------------------------------------
# Condition evaluation
# ------------------------------------------------------------------


def evaluate_conditions(node: dict[str, Any], ctx: ExecutionContext) -> bool:
    """Recursively evaluate a condition tree. Returns True if conditions pass."""
    if not node:
        return True  # empty conditions = always match

    node_type = node.get("type")

    match node_type:
        case "and":
            return all(evaluate_conditions(child, ctx) for child in node.get("children", []))
        case "or":
            return any(evaluate_conditions(child, ctx) for child in node.get("children", []))
        case "not":
            children = node.get("children", [])
            if not children:
                return True
            return not evaluate_conditions(children[0], ctx)
        case "compare":
            return _evaluate_compare(node, ctx)
        case _:
            raise RuleError(f"Unknown condition type: {node_type!r}")


def _evaluate_compare(node: dict[str, Any], ctx: ExecutionContext) -> bool:
    op = node.get("op")
    if op not in _COMPARE_OPS:
        raise RuleError(f"Unknown compare operator: {op!r}")

    field_name = node.get("field")
    if not isinstance(field_name, str):
        raise RuleError("compare condition requires a string 'field' name")
    actual = ctx.record.get(field_name)

    # value can be an expression node or a raw literal
    value_node = node.get("value")
    expected = evaluate(value_node, ctx.record) if isinstance(value_node, dict) else value_node

    return _compare(actual, op, expected)


def _compare(actual: Any, op: str, expected: Any) -> bool:
    match op:
        case "eq":
            return bool(actual == expected)
        case "ne":
            return bool(actual != expected)
        case "is_null":
            return actual is None
        case "is_not_null":
            return actual is not None
        case "contains":
            return expected in str(actual or "")
        case "icontains":
            return expected.lower() in str(actual or "").lower()
        case "starts_with":
            return str(actual or "").startswith(str(expected or ""))
        case "ends_with":
            return str(actual or "").endswith(str(expected or ""))
        case "in":
            vals = expected if isinstance(expected, list) else str(expected).split(",")
            return actual in vals
        case "nin":
            vals = expected if isinstance(expected, list) else str(expected).split(",")
            return actual not in vals
        case _:
            # Numeric comparisons
            try:
                a, e = float(actual), float(expected)
            except (TypeError, ValueError):
                return False
            match op:
                case "gt":
                    return a > e
                case "gte":
                    return a >= e
                case "lt":
                    return a < e
                case "lte":
                    return a <= e
                case _:
                    return False


# ------------------------------------------------------------------
# Action execution (pure — returns mutations, no DB calls)
# ------------------------------------------------------------------


def execute_actions(actions: list[dict[str, Any]], ctx: ExecutionContext) -> ExecutionResult:
    result = ExecutionResult(matched=True)

    if len(actions) > _MAX_ACTIONS:
        raise RuleError(f"Rule exceeds maximum of {_MAX_ACTIONS} actions")

    for action in actions:
        if result.stopped:
            break
        try:
            _execute_action(action, ctx, result)
        except (ExpressionError, RuleError) as exc:
            result.errors.append(str(exc))
            # Non-fatal: log error, continue with remaining actions
        except Exception as exc:
            result.errors.append(f"Unexpected error in action: {exc}")

    # Apply field mutations back to context record for downstream actions
    ctx.record.update(result.field_mutations)

    return result


def _execute_action(action: dict[str, Any], ctx: ExecutionContext, result: ExecutionResult) -> None:
    atype = action.get("type")

    match atype:
        case "set_field":
            field_name = action.get("field")
            if not isinstance(field_name, str):
                raise RuleError("set_field.field must be a string")
            value = evaluate(action.get("value", {"type": "literal", "value": None}), ctx.record)
            result.field_mutations[field_name] = value

        case "create_record":
            payload = {
                k: evaluate(v, ctx.record) if isinstance(v, dict) else v
                for k, v in action.get("payload", {}).items()
            }
            entry: dict[str, Any] = {
                "entity_id": action.get("entity_id"),
                "payload": payload,
            }
            # `match`/`increment` make this an upsert — see CreateRecordAction's
            # docstring. Evaluated the same way as `payload` (literals or
            # expressions over the triggering record), then handed to the
            # sandbox worker's persistence step, which does the actual DB
            # find-or-increment (this interpreter stays DB-free by design).
            match = action.get("match")
            if match:
                entry["match"] = {
                    k: evaluate(v, ctx.record) if isinstance(v, dict) else v
                    for k, v in match.items()
                }
            increment = action.get("increment")
            if increment:
                entry["increment"] = {
                    k: evaluate(v, ctx.record) if isinstance(v, dict) else v
                    for k, v in increment.items()
                }
            result.records_to_create.append(entry)

        case "update_record":
            id_field = action.get("record_id_field", "id")
            record_id = ctx.record.get(id_field)
            if not record_id:
                raise RuleError(f"update_record: field {id_field!r} not found in record")
            payload = {
                k: evaluate(v, ctx.record) if isinstance(v, dict) else v
                for k, v in action.get("payload", {}).items()
            }
            result.records_to_update.append({"record_id": str(record_id), "payload": payload})

        case "delete_record":
            id_field = action.get("record_id_field", "id")
            record_id = ctx.record.get(id_field)
            if record_id:
                result.records_to_delete.append(str(record_id))

        case "send_notification":
            to_field = action.get("to_field")
            recipient = ctx.record.get(to_field) if to_field else action.get("to")
            result.notifications.append(
                {
                    "to": recipient,
                    "subject": action.get("subject", ""),
                    "template": action.get("template", ""),
                    "context": dict(ctx.record),
                }
            )

        case "call_webhook":
            # Dispatched to notifications queue, not executed inline in sandbox
            payload = {
                k: evaluate(v, ctx.record) if isinstance(v, dict) else v
                for k, v in action.get("payload", {}).items()
            }
            result.webhooks.append(
                {
                    "url": action.get("url"),
                    "method": action.get("method", "POST"),
                    "payload": payload,
                }
            )

        case "stop":
            result.stopped = True

        case _:
            raise RuleError(f"Unknown action type: {atype!r}")


# ------------------------------------------------------------------
# Top-level entry point
# ------------------------------------------------------------------


def run_rule(
    rule_trigger: dict[str, Any],
    rule_conditions: dict[str, Any],
    rule_actions: list[dict[str, Any]],
    ctx: ExecutionContext,
) -> ExecutionResult:
    """
    Evaluate a single rule against the given context.
    Returns ExecutionResult — caller is responsible for persisting mutations.
    """
    # Check trigger event matches
    trigger_event = rule_trigger.get("event", "")
    # "field.changed" is a sub-event of "record.updated"
    if (
        trigger_event
        and trigger_event != ctx.event
        and not (trigger_event == "field.changed" and ctx.event == "record.updated")
    ):
        return ExecutionResult(matched=False)

    # For field.changed: verify at least one watched field actually changed
    if trigger_event == "field.changed":
        watch_fields = set(rule_trigger.get("watch_fields", []))
        if watch_fields and not (watch_fields & set(ctx.changed_fields)):
            return ExecutionResult(matched=False)

    # Evaluate conditions tree
    try:
        if not evaluate_conditions(rule_conditions, ctx):
            return ExecutionResult(matched=False)
    except RuleError as exc:
        result = ExecutionResult(matched=False)
        result.errors.append(f"Condition error: {exc}")
        return result

    # Execute actions
    return execute_actions(rule_actions, ctx)


# ------------------------------------------------------------------
# Batch evaluation — all rules matching one event, evaluated together so
# priority-based conflict resolution (ТЗ 3.5.4) is actually possible.
# ------------------------------------------------------------------


@dataclass
class RuleOutcome:
    rule_id: str
    result: ExecutionResult
    overridden_fields: list[str] = field(default_factory=list)  # this rule's writes that lost


@dataclass
class FieldConflict:
    field_name: str
    winning_rule_id: str
    winning_value: Any
    losing_writes: list[dict[str, Any]]  # [{"rule_id": ..., "value": ...}, ...]


@dataclass
class BatchResult:
    outcomes: list[RuleOutcome] = field(default_factory=list)
    applied_mutations: dict[str, Any] = field(default_factory=dict)
    conflicts: list[FieldConflict] = field(default_factory=list)
    records_to_create: list[dict[str, Any]] = field(default_factory=list)
    records_to_update: list[dict[str, Any]] = field(default_factory=list)
    records_to_delete: list[str] = field(default_factory=list)
    notifications: list[dict[str, Any]] = field(default_factory=list)
    webhooks: list[dict[str, Any]] = field(default_factory=list)


def run_rules_batch(
    rules: list[dict[str, Any]],
    ctx: ExecutionContext,
) -> BatchResult:
    """
    Evaluate all `rules` against one shared context, in the order given
    (callers must sort by priority ascending — lower number runs first).

    Field-level conflicts (two rules setting the same field to different
    values) resolve in favor of whichever rule ran first in `rules` — i.e.
    whichever has the higher priority. `execute_actions` unconditionally
    folds a rule's own mutations into `ctx.record`, so a losing write is
    reverted immediately after being detected, keeping later rules'
    conditions evaluated against the correct (winning) field values.
    """
    batch = BatchResult()
    applied_by: dict[str, str] = {}  # field -> rule_id that won it
    conflicts_by_field: dict[str, FieldConflict] = {}

    for rule in rules:
        rule_id = str(rule["id"])
        result = run_rule(rule["trigger"], rule["conditions"], rule["actions"], ctx)
        overridden: list[str] = []

        if result.matched:
            for field_name, value in result.field_mutations.items():
                if field_name not in applied_by:
                    batch.applied_mutations[field_name] = value
                    applied_by[field_name] = rule_id
                elif batch.applied_mutations[field_name] != value:
                    overridden.append(field_name)
                    conflict = conflicts_by_field.get(field_name)
                    if conflict is None:
                        conflict = FieldConflict(
                            field_name=field_name,
                            winning_rule_id=applied_by[field_name],
                            winning_value=batch.applied_mutations[field_name],
                            losing_writes=[],
                        )
                        conflicts_by_field[field_name] = conflict
                    conflict.losing_writes.append({"rule_id": rule_id, "value": value})
                    # execute_actions() already wrote `value` into ctx.record —
                    # put the winning value back so downstream rules see it.
                    ctx.record[field_name] = batch.applied_mutations[field_name]
                # else: identical value proposed twice — not a real conflict.

            batch.records_to_create.extend(result.records_to_create)
            batch.records_to_update.extend(result.records_to_update)
            batch.records_to_delete.extend(result.records_to_delete)
            batch.notifications.extend(result.notifications)
            batch.webhooks.extend(result.webhooks)

        batch.outcomes.append(
            RuleOutcome(rule_id=rule_id, result=result, overridden_fields=overridden)
        )

    batch.conflicts = list(conflicts_by_field.values())
    return batch
