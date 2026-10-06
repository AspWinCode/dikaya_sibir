"""Rule schemas + typed AST validation."""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


# ------------------------------------------------------------------
# Trigger
# ------------------------------------------------------------------

class RuleType(str, Enum):
    AUTOMATION = "automation"
    AUTOFILL   = "autofill"
    VALIDATION = "validation"


class TriggerEvent(str, Enum):
    RECORD_CREATED = "record.created"
    RECORD_UPDATED = "record.updated"
    RECORD_DELETED = "record.deleted"
    FIELD_CHANGED  = "field.changed"
    SCHEDULE       = "schedule"


class ScheduleKind(str, Enum):
    CRON = "cron"                    # calendar tick, e.g. "monthly on the 1st" (ТЗ: ежемесячная амортизация)
    RELATIVE_DATE = "relative_date"  # N days before/after a per-record date field (ТЗ: напоминание за 3 дня до срока)


class CronSchedule(BaseModel):
    """Fields mirror celery.schedules.crontab. Checked hourly (see
    app/worker/tasks/rules_schedule.py), so `minute` only matters as
    "0" (fires on the hour) vs anything else (never fires) — sub-hour
    granularity isn't supported."""
    minute: str = "0"
    hour: str = "0"
    day_of_month: str = "*"
    month_of_year: str = "*"
    day_of_week: str = "*"


class RelativeDateSchedule(BaseModel):
    date_field: str = Field(min_length=1, max_length=128)
    offset_days: int = Field(
        ge=-365, le=365,
        description="Negative = before the date (a reminder), positive = after. "
                     "-3 fires once when today == date_field - 3 days.",
    )


class RuleTrigger(BaseModel):
    event: TriggerEvent
    watch_fields: list[str] = Field(
        default_factory=list,
        description="For field.changed: only fire if these fields were modified",
    )
    schedule_kind: ScheduleKind | None = None
    cron: CronSchedule | None = None
    relative_date: RelativeDateSchedule | None = None

    @model_validator(mode="after")
    def validate_schedule(self) -> "RuleTrigger":
        if self.event == TriggerEvent.SCHEDULE:
            if self.schedule_kind == ScheduleKind.CRON:
                if not self.cron:
                    raise ValueError("trigger.cron is required when schedule_kind='cron'")
            elif self.schedule_kind == ScheduleKind.RELATIVE_DATE:
                if not self.relative_date:
                    raise ValueError("trigger.relative_date is required when schedule_kind='relative_date'")
            else:
                raise ValueError("trigger.schedule_kind ('cron' or 'relative_date') is required when event='schedule'")
        elif self.schedule_kind or self.cron or self.relative_date:
            raise ValueError("schedule_kind/cron/relative_date are only valid when event='schedule'")
        return self


# ------------------------------------------------------------------
# Condition AST
# ------------------------------------------------------------------

class CompareOp(str, Enum):
    EQ          = "eq"
    NE          = "ne"
    GT          = "gt"
    GTE         = "gte"
    LT          = "lt"
    LTE         = "lte"
    CONTAINS    = "contains"
    ICONTAINS   = "icontains"
    IN          = "in"
    NIN         = "nin"
    IS_NULL     = "is_null"
    IS_NOT_NULL = "is_not_null"
    STARTS_WITH = "starts_with"
    ENDS_WITH   = "ends_with"


class CompareCondition(BaseModel):
    type: Literal["compare"]
    field: str
    op: CompareOp
    value: Any = None


class LogicalCondition(BaseModel):
    type: Literal["and", "or", "not"]
    children: list["ConditionNode"] = Field(default_factory=list)


ConditionNode = CompareCondition | LogicalCondition
LogicalCondition.model_rebuild()


# ------------------------------------------------------------------
# Expression AST
# ------------------------------------------------------------------

class LiteralExpr(BaseModel):
    type: Literal["literal"]
    value: Any


class FieldRefExpr(BaseModel):
    type: Literal["field_ref"]
    field: str


class MathOp(str, Enum):
    ADD      = "add"
    SUBTRACT = "subtract"
    MULTIPLY = "multiply"
    DIVIDE   = "divide"
    MODULO   = "modulo"
    POWER    = "power"


class MathExpr(BaseModel):
    type: Literal["math"]
    op: MathOp
    left: "ExprNode"
    right: "ExprNode"


class FuncExpr(BaseModel):
    type: Literal["func"]
    name: str
    args: list["ExprNode"] = Field(default_factory=list)


class LookupAgg(str, Enum):
    VALUE = "value"  # first matching record's field
    SUM   = "sum"
    COUNT = "count"
    AVG   = "avg"
    MIN   = "min"
    MAX   = "max"


class LookupExpr(BaseModel):
    """Reads a value from a DIFFERENT entity's records — the cross-table
    primitive validation rules need (ТЗ: "проверка достаточности материалов
    по рецепту"). `filter` maps a target field name to an expression
    evaluated against the *triggering* record (so it can reference the
    record's own fields, incl. another lookup for chained hops — a
    filter's own field_ref/lookup is resolved before this lookup runs).
    Only used inside a validation rule's condition/action value — the main
    interpreter's pure evaluate() never sees an unresolved "lookup" node,
    see app/engine/lookup.py."""
    type: Literal["lookup"]
    entity_id: uuid.UUID
    filter: dict[str, Any] = Field(default_factory=dict)
    field: str | None = None  # omit for agg="count"
    agg: LookupAgg = LookupAgg.VALUE


ExprNode = LiteralExpr | FieldRefExpr | MathExpr | FuncExpr | LookupExpr
MathExpr.model_rebuild()
FuncExpr.model_rebuild()


# ------------------------------------------------------------------
# Action AST
# ------------------------------------------------------------------

class SetFieldAction(BaseModel):
    type: Literal["set_field"]
    field: str
    value: Any  # ExprNode or literal


class CreateRecordAction(BaseModel):
    """`match`/`increment` turn this into a generic upsert: if a record in
    `entity_id` already matches every `match` field (exact equality, after
    expression evaluation), its `increment` fields are added to (numeric
    delta — negative to subtract) instead of creating a new record. Without
    `match`, behaves exactly as before — always creates. This is the
    building block for "running balance" entities (e.g. a Product×Location
    stock table fed by receipt/transfer records) without a bespoke action
    type or app-specific code — see ТЗ item 13."""
    type: Literal["create_record"]
    entity_id: uuid.UUID
    payload: dict[str, Any] = Field(default_factory=dict)
    match: dict[str, Any] | None = None
    increment: dict[str, Any] | None = None


class UpdateRecordAction(BaseModel):
    type: Literal["update_record"]
    record_id_field: str = "id"
    payload: dict[str, Any] = Field(default_factory=dict)


class DeleteRecordAction(BaseModel):
    type: Literal["delete_record"]
    record_id_field: str = "id"


class SendNotificationAction(BaseModel):
    type: Literal["send_notification"]
    to_field: str | None = None
    to: str | None = None
    subject: str = ""
    template: str = ""


class CallWebhookAction(BaseModel):
    type: Literal["call_webhook"]
    url: str
    method: str = "POST"
    payload: dict[str, Any] = Field(default_factory=dict)


class StopAction(BaseModel):
    type: Literal["stop"]


class BlockSaveAction(BaseModel):
    """Validation-rule-only action: rejects the save with a 422 carrying
    `message`. Only meaningful on a rule_type="validation" rule — see
    app/services/validation_rules.py, which runs these synchronously
    *before* the record is written, unlike every other action here."""
    type: Literal["block_save"]
    message: str = Field(default="Сохранение отклонено правилом проверки", max_length=500)


ActionNode = (
    SetFieldAction
    | CreateRecordAction
    | UpdateRecordAction
    | DeleteRecordAction
    | SendNotificationAction
    | CallWebhookAction
    | StopAction
    | BlockSaveAction
)


# ------------------------------------------------------------------
# Rule schemas
# ------------------------------------------------------------------

class RuleRead(BaseModel):
    id: uuid.UUID
    app_id: uuid.UUID
    entity_id: uuid.UUID
    name: str
    description: str | None
    is_active: bool
    rule_type: RuleType = RuleType.AUTOMATION
    trigger: dict[str, Any]
    conditions: dict[str, Any]
    actions: list[dict[str, Any]]
    priority: int
    version: int
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class RuleCreate(BaseModel):
    entity_id: uuid.UUID
    name: str = Field(min_length=2, max_length=256)
    description: str | None = None
    rule_type: RuleType = RuleType.AUTOMATION
    trigger: RuleTrigger
    conditions: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    priority: int = Field(default=100, ge=1, le=9999)

    @model_validator(mode="after")
    def validate_ast(self) -> "RuleCreate":
        # Validate conditions structure
        if self.conditions:
            _validate_condition_node(self.conditions)
        # Validate actions structure
        for action in self.actions:
            _validate_action_node(action)
        _validate_rule_type_actions(self.rule_type, self.actions)
        return self


class RuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=256)
    description: str | None = None
    rule_type: RuleType | None = None
    trigger: RuleTrigger | None = None
    conditions: dict[str, Any] | None = None
    actions: list[dict[str, Any]] | None = None
    priority: int | None = Field(default=None, ge=1, le=9999)
    is_active: bool | None = None


class RuleTestRequest(BaseModel):
    """Dry-run a rule against a sample record payload without persisting changes."""
    record_payload: dict[str, Any]
    event: str = "record.updated"
    changed_fields: list[str] = Field(default_factory=list)


class RuleTestResponse(BaseModel):
    matched: bool
    field_mutations: dict[str, Any]
    records_to_create: list[dict[str, Any]]
    notifications: list[dict[str, Any]]
    webhooks: list[dict[str, Any]]
    errors: list[str]


class RuleExecutionLogRead(BaseModel):
    id: uuid.UUID
    rule_id: uuid.UUID
    record_id: uuid.UUID | None
    event: str
    status: str
    duration_ms: int | None
    error: str | None
    output_snapshot: dict[str, Any] | None
    executed_at: datetime
    model_config = {"from_attributes": True}


class CycleCheckResponse(BaseModel):
    has_cycles: bool
    cycles: list[list[str]]  # list of rule_id lists that form cycles


class RuleConflictLogRead(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    record_id: uuid.UUID
    event: str
    field_name: str
    winning_rule_id: uuid.UUID
    winning_value: Any
    losing_writes: list[dict[str, Any]]
    execution_batch_id: uuid.UUID
    detected_at: datetime
    model_config = {"from_attributes": True}


class RuleWebhookDeliveryRead(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    record_id: uuid.UUID | None
    execution_batch_id: uuid.UUID
    url: str
    method: str
    status: str
    status_code: int | None
    error: str | None
    attempt_count: int
    created_at: datetime
    model_config = {"from_attributes": True}


# ------------------------------------------------------------------
# AST validation helpers (lightweight, not full type-checking)
# ------------------------------------------------------------------

_VALID_CONDITION_TYPES = {"and", "or", "not", "compare"}
_VALID_ACTION_TYPES = {
    "set_field", "create_record", "update_record", "delete_record",
    "send_notification", "call_webhook", "stop", "block_save",
}
_VALID_EXPR_TYPES = {"literal", "field_ref", "math", "func", "lookup"}
_VALID_LOOKUP_AGGS = {"value", "sum", "count", "avg", "min", "max"}


def _validate_expr_node(node: Any, depth: int = 0) -> None:
    if depth > 15:
        raise ValueError("Expression tree too deep (max 15)")
    if not isinstance(node, dict):
        return  # a raw literal — always valid
    t = node.get("type")
    if t not in _VALID_EXPR_TYPES:
        raise ValueError(f"Invalid expression type: {t!r}")
    if t == "math":
        _validate_expr_node(node.get("left"), depth + 1)
        _validate_expr_node(node.get("right"), depth + 1)
    elif t == "func":
        for arg in node.get("args", []):
            _validate_expr_node(arg, depth + 1)
    elif t == "lookup":
        if not node.get("entity_id"):
            raise ValueError("lookup.entity_id is required")
        if node.get("agg", "value") not in _VALID_LOOKUP_AGGS:
            raise ValueError(f"Invalid lookup.agg: {node.get('agg')!r}")
        if node.get("agg", "value") != "count" and not node.get("field"):
            raise ValueError("lookup.field is required unless agg is 'count'")
        for v in (node.get("filter") or {}).values():
            _validate_expr_node(v, depth + 1)


def _validate_condition_node(node: Any, depth: int = 0) -> None:
    if depth > 20:
        raise ValueError("Condition tree too deep (max 20)")
    if not isinstance(node, dict):
        raise ValueError("Condition node must be a dict")
    t = node.get("type")
    if t not in _VALID_CONDITION_TYPES:
        raise ValueError(f"Invalid condition type: {t!r}")
    if t == "compare" and isinstance(node.get("value"), dict):
        _validate_expr_node(node["value"])
    for child in node.get("children", []):
        _validate_condition_node(child, depth + 1)


def _validate_rule_type_actions(rule_type: "RuleType", actions: list[dict[str, Any]]) -> None:
    """block_save only does anything inside ValidationRuleService's
    synchronous pre-commit pass (app/services/validation_rules.py) — the
    async interpreter used by automation/autofill rules has no case for it
    and would just log a silent "unknown action type" error. Conversely a
    validation rule's non-block_save actions (set_field etc.) are simply
    never looked at by that service — reject both mismatches up front
    instead of letting them silently do nothing."""
    has_block_save = any(a.get("type") == "block_save" for a in actions)
    if rule_type == RuleType.VALIDATION:
        if actions and not all(a.get("type") == "block_save" for a in actions):
            raise ValueError("A validation rule's actions may only be block_save")
    elif has_block_save:
        raise ValueError("block_save is only valid on a validation rule (rule_type=\"validation\")")


def _validate_action_node(node: Any) -> None:
    if not isinstance(node, dict):
        raise ValueError("Action node must be a dict")
    t = node.get("type")
    if t not in _VALID_ACTION_TYPES:
        raise ValueError(f"Invalid action type: {t!r}")
    if t == "set_field" and isinstance(node.get("value"), dict):
        _validate_expr_node(node["value"])


# ------------------------------------------------------------------
# Process steps — an ordered, editable view over rule.actions
# ------------------------------------------------------------------
#
# A "step" is a friendlier projection of an action node for the UI:
#   node  = {"id": "...", "type": "set_field", "field": "x", "value": 1}
#   step  = {"id": "...", "type": "set_field", "config": {"field": "x", "value": 1}, "order": 0}
# `order` is the position in the actions array. The extra `id` key is ignored
# by the interpreter (it dispatches on `type` only), so storing it is safe.

MAX_STEPS = 20
_STEP_RESERVED_KEYS = {"id", "type"}


class ProcessStepRead(BaseModel):
    id: str
    order: int
    type: str
    config: dict[str, Any] = Field(default_factory=dict)


class ProcessStepCreate(BaseModel):
    type: str
    config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_step(self) -> "ProcessStepCreate":
        _validate_action_node(step_to_node(self.type, self.config))
        return self


class ProcessStepUpdate(BaseModel):
    type: str | None = None
    config: dict[str, Any] | None = None


class ProcessStepsReorder(BaseModel):
    step_ids: list[str] = Field(min_length=0)


def step_to_node(type_: str, config: dict[str, Any] | None, step_id: str | None = None) -> dict[str, Any]:
    """Flatten a (type, config) step into a stored action node with a stable id."""
    node = {k: v for k, v in (config or {}).items() if k not in _STEP_RESERVED_KEYS}
    node["type"] = type_
    node["id"] = step_id or str(uuid.uuid4())
    return node


def node_to_step(node: dict[str, Any], order: int) -> ProcessStepRead:
    """Project a stored action node into a ProcessStepRead."""
    config = {k: v for k, v in node.items() if k not in _STEP_RESERVED_KEYS}
    return ProcessStepRead(
        id=str(node.get("id", "")),
        order=order,
        type=str(node.get("type", "")),
        config=config,
    )


def ensure_step_ids(actions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Backfill a stable id for any legacy action node missing one.

    Returns (normalised_actions, changed)."""
    out: list[dict[str, Any]] = []
    changed = False
    for node in actions or []:
        node = dict(node)
        if not node.get("id"):
            node["id"] = str(uuid.uuid4())
            changed = True
        out.append(node)
    return out, changed
