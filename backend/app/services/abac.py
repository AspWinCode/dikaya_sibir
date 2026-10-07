"""
Row-level ABAC (AbacRule) — condition grammar shared by record enforcement
(app/services/records.py) and rule validation (app/services/roles.py).

A condition is `{"field": str, "op": str, "value": ...}`. `field` is either
an author field (compared against the Record.created_by column) or any
other name (read from the record's JSONB payload). `value` may be a
literal, a list of literals (for in/not_in), or a "$self.<attr>" token
resolved from the acting user at evaluation time (see SELF_ATTRS).

ТЗ 3.1.4: "видимость и редактируемость записей на основе условий
(например, «пользователь видит только записи своего отдела»)". Records
don't carry a fixed "department" — the closest built-in attribute is the
user's organisation, so `$self.org_id` is what a rule like that example
is built from today (e.g. `{"field": "department_id", "op": "eq",
"value": "$self.org_id"}` once an org-scoped deployment uses org_id as its
department key). Arbitrary literal-value conditions on any payload field
are also supported, e.g. `{"field": "status", "op": "in", "value": [...]}`.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Numeric

logger = structlog.get_logger(__name__)

AUTHOR_FIELD_NAMES = {"author_id", "created_by"}
SELF_ATTRS = {"id", "org_id", "email"}
# Attrs beyond "id" require a User row lookup — "id" comes for free from the caller.
_LOOKUP_ATTRS = SELF_ATTRS - {"id"}
COMPARISON_OPS = {"eq", "ne", "in", "not_in", "contains", "gt", "gte", "lt", "lte"}
# Accepted aliases from the rule editor UI, normalized to the canonical op above.
_OP_ALIASES = {"neq": "ne", "nin": "not_in"}


class AbacConditionError(ValueError):
    """A condition's field/op/value shape can't be evaluated."""


def _jsonb_text(payload_column: Any, field: str) -> Any:
    return func.jsonb_extract_path_text(payload_column, field)


def _normalize_op(op: Any) -> Any:
    return _OP_ALIASES.get(op, op)


def validate_condition(cond: Any) -> None:
    """Raise AbacConditionError if `cond` isn't a shape `condition_to_sql` can
    evaluate. Called when an AbacRule is created/updated so a bad rule fails
    loudly at save time instead of silently no-op'ing during enforcement."""
    if not isinstance(cond, dict):
        raise AbacConditionError("ABAC condition must be an object")
    field_name = cond.get("field")
    op = _normalize_op(cond.get("op", "eq"))
    value = cond.get("value")
    if not field_name or not isinstance(field_name, str):
        raise AbacConditionError("ABAC condition requires a non-empty 'field'")
    if op not in COMPARISON_OPS:
        raise AbacConditionError(
            f"Unsupported ABAC operator {cond.get('op')!r}; must be one of {sorted(COMPARISON_OPS)}"
        )
    if op in {"in", "not_in"} and not isinstance(value, list):
        raise AbacConditionError(f"Operator {op!r} requires a list value")
    if op in {"gt", "gte", "lt", "lte", "contains"} and field_name in AUTHOR_FIELD_NAMES:
        raise AbacConditionError(f"Operator {op!r} is not supported on {field_name!r}")

    def _check_token(v: Any) -> None:
        if not isinstance(v, str) or not (v == "$self" or v.startswith("$self.")):
            return
        attr = "id" if v == "$self" else v[len("$self.") :]
        if attr not in SELF_ATTRS:
            raise AbacConditionError(
                f"Unsupported $self attribute {v!r}; must be one of "
                f"{sorted('$self.' + a for a in SELF_ATTRS)}"
            )

    for v in value if isinstance(value, list) else [value]:
        _check_token(v)


def referenced_self_attrs(cond: Any) -> set[str]:
    """Which of _LOOKUP_ATTRS this condition's value(s) reference, if any."""
    if not isinstance(cond, dict):
        return set()
    value = cond.get("value")
    tokens = value if isinstance(value, list) else [value]
    attrs = set()
    for v in tokens:
        if isinstance(v, str) and v.startswith("$self.") and v[len("$self.") :] in _LOOKUP_ATTRS:
            attrs.add(v[len("$self.") :])
    return attrs


def _resolve_self_token(token: Any, self_ctx: dict[str, str | None]) -> Any:
    if not isinstance(token, str) or not (
        token == "$self" or token.startswith("$self.")  # noqa: S105
    ):
        return token
    attr = "id" if token == "$self" else token[len("$self.") :]  # noqa: S105
    if attr not in SELF_ATTRS:
        return None
    return self_ctx.get(attr)


def condition_to_sql(
    cond: dict, self_ctx: dict[str, str | None], *, record_model: Any
) -> Any | None:
    """Build a SQLAlchemy WHERE clause for one condition, or None if it can't
    be evaluated (unsupported shape, or a $self token that didn't resolve —
    e.g. an anonymous actor, or a user with no organisation)."""
    if not isinstance(cond, dict):
        return None
    field_name = cond.get("field")
    op = _normalize_op(cond.get("op", "eq"))
    raw_value = cond.get("value")
    if not field_name or not isinstance(field_name, str):
        return None

    if isinstance(raw_value, list):
        resolved = [_resolve_self_token(v, self_ctx) for v in raw_value]
        if any(v is None for v in resolved):
            logger.warning("abac_condition_unresolved", condition=cond)
            return None
        value: Any = [str(v) for v in resolved]
    else:
        resolved_one = _resolve_self_token(raw_value, self_ctx)
        if resolved_one is None:
            logger.warning("abac_condition_unresolved", condition=cond)
            return None
        value = str(resolved_one)

    is_author_field = field_name in AUTHOR_FIELD_NAMES
    if is_author_field:
        try:
            cmp_value: Any = (
                [uuid.UUID(v) for v in value] if isinstance(value, list) else uuid.UUID(value)
            )
        except (ValueError, TypeError):
            logger.warning("abac_condition_unsupported", condition=cond)
            return None
        expr = record_model.created_by
    else:
        expr = _jsonb_text(record_model.payload, field_name)
        cmp_value = value

    match op:
        case "eq":
            return expr == cmp_value
        case "ne":
            return expr != cmp_value
        case "in":
            return expr.in_(cmp_value if isinstance(cmp_value, list) else [cmp_value])
        case "not_in":
            return expr.notin_(cmp_value if isinstance(cmp_value, list) else [cmp_value])
        case "contains" if not is_author_field:
            return expr.contains(cmp_value)
        case "gt" | "gte" | "lt" | "lte" if not is_author_field:
            try:
                numeric_value = float(cmp_value)
            except (TypeError, ValueError):
                logger.warning("abac_condition_unsupported", condition=cond)
                return None
            numeric_expr = cast(expr, Numeric)
            if op == "gt":
                return numeric_expr > numeric_value
            if op == "gte":
                return numeric_expr >= numeric_value
            if op == "lt":
                return numeric_expr < numeric_value
            return numeric_expr <= numeric_value
        case _:
            logger.warning("abac_condition_unsupported", condition=cond)
            return None


def _rule_clause(rule: Any, self_ctx: dict[str, str | None], *, record_model: Any) -> Any | None:
    """AND together every condition on one rule; None if any condition can't
    be evaluated (the whole rule is then skipped rather than partially
    applied)."""
    clauses = []
    for cond in rule.condition_json or []:
        sql_cond = condition_to_sql(cond, self_ctx, record_model=record_model)
        if sql_cond is None:
            return None
        clauses.append(sql_cond)
    if not clauses:
        return None
    return and_(*clauses) if len(clauses) > 1 else clauses[0]


async def apply_row_scope(
    db: AsyncSession,
    stmt: Any,
    entity_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    actor_roles: list[str] | None,
    *,
    record_model: Any,
    abac_rule_model: Any,
    user_model: Any,
) -> Any:
    """Restrict a record query per AbacRule rows targeting this entity and one
    of the caller's roles. "allow" rules scope visibility to the union of
    their conditions; "deny" rules exclude matching rows and win over any
    "allow". No matching rules = no restriction (open by default)."""
    if not actor_roles:
        return stmt
    result = await db.execute(
        select(abac_rule_model).where(
            abac_rule_model.resource_type == "entity",
            or_(
                abac_rule_model.resource_id.is_(None), abac_rule_model.resource_id == str(entity_id)
            ),
            abac_rule_model.role_id.in_(actor_roles),
        )
    )
    rules = result.scalars().all()
    if not rules:
        return stmt

    self_ctx: dict[str, str | None] = {attr: None for attr in SELF_ATTRS}
    self_ctx["id"] = str(actor_id) if actor_id else None

    needed_attrs: set[str] = set()
    for rule in rules:
        for cond in rule.condition_json or []:
            needed_attrs |= referenced_self_attrs(cond)
    if needed_attrs and actor_id is not None:
        columns = [getattr(user_model, attr) for attr in sorted(needed_attrs)]
        row = (await db.execute(select(*columns).where(user_model.id == actor_id))).one_or_none()
        if row is not None:
            for attr, value in zip(sorted(needed_attrs), row, strict=False):
                self_ctx[attr] = str(value) if value is not None else None

    allow_clauses: list[Any] = []
    deny_clauses: list[Any] = []
    for rule in rules:
        clause = _rule_clause(rule, self_ctx, record_model=record_model)
        if clause is None:
            continue
        (deny_clauses if rule.effect == "deny" else allow_clauses).append(clause)

    if allow_clauses:
        stmt = stmt.where(or_(*allow_clauses))
    for clause in deny_clauses:
        stmt = stmt.where(~clause)
    return stmt
