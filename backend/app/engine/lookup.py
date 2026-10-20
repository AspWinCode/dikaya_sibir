"""Cross-table lookups (ТЗ: "проверка достаточности материалов по рецепту
при сохранении детали отчёта"; also used by automation rules writing an
aggregated value into a related record — e.g. "сумма операций по
работнику").

The main Rules Engine interpreter (app/engine/interpreter.py) and expression
evaluator (app/engine/expressions.py) are deliberately pure/synchronous — no
I/O, no DB — by design (see RULES_AND_WORKFLOW.md principle 4). A "lookup"
expression node needs to query a *different* entity's records, which is
inherently async DB I/O, so it can't live inside that pure evaluator.

Instead: before handing a rule's conditions/actions to the pure interpreter,
`resolve_lookups()` walks the AST and replaces every unresolved
{"type": "lookup", ...} node with a plain {"type": "literal", "value": ...}
node (querying the DB to compute that value). The interpreter then evaluates
the resulting tree exactly as it always has, none the wiser that a "lookup"
ever existed. This also gives chained lookups "for free": a lookup used
inside another lookup's `filter` is resolved bottom-up by the same recursion,
so "деталь_отчёта -> рецепт -> номенклатура" is just two nested lookup nodes.

Validation rules resolve their *conditions* this way synchronously,
in-process, before commit (app/services/validation_rules.py). Automation
rules — dispatched async to the sandbox Celery worker, which has no event
loop/DB session until it builds one itself — resolve lookups inside their
*actions* (and conditions) via `resolve_rule_lookups()` below, called from
app/worker/tasks/sandbox.py before the pure interpreter runs.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.expressions import evaluate
from app.engine.interpreter import ExecutionContext, RuleError
from app.models.data import Record


class RuleLookupError(Exception):
    pass


def _jsonb_text(field: str) -> Any:
    return func.jsonb_extract_path_text(Record.payload, field)


async def resolve_lookups(node: Any, db: AsyncSession, ctx: ExecutionContext) -> Any:
    """Return a copy of `node` with every "lookup" subtree replaced by a
    "literal" node. Non-dict values (raw literals) and unrelated node types
    pass through unchanged; recognized composite node types recurse into
    their expression-bearing fields so a lookup nested anywhere resolves."""
    if not isinstance(node, dict):
        return node

    node_type = node.get("type")

    if node_type == "lookup":
        value = await _execute_lookup(node, db, ctx)
        return {"type": "literal", "value": value}

    if node_type in ("and", "or", "not"):
        return {
            **node,
            "children": [await resolve_lookups(c, db, ctx) for c in node.get("children", [])],
        }

    if node_type == "compare":
        new_node = dict(node)
        if isinstance(node.get("value"), dict):
            new_node["value"] = await resolve_lookups(node["value"], db, ctx)
        return new_node

    if node_type == "math":
        new_node = dict(node)
        new_node["left"] = await resolve_lookups(node.get("left"), db, ctx)
        new_node["right"] = await resolve_lookups(node.get("right"), db, ctx)
        return new_node

    if node_type == "func":
        return {
            **node,
            "args": [await resolve_lookups(a, db, ctx) for a in node.get("args", [])],
        }

    # "literal" / "field_ref" / unknown — nothing to resolve
    return node


async def _execute_lookup(node: dict[str, Any], db: AsyncSession, ctx: ExecutionContext) -> Any:
    entity_id_raw = node.get("entity_id")
    if not entity_id_raw:
        raise RuleLookupError("lookup.entity_id is required")
    try:
        entity_id = uuid.UUID(str(entity_id_raw))
    except ValueError as exc:
        raise RuleLookupError(f"lookup.entity_id is not a valid UUID: {entity_id_raw!r}") from exc

    agg = node.get("agg", "value")
    field_name = node.get("field")
    if agg != "count" and not field_name:
        raise RuleLookupError("lookup.field is required unless agg is 'count'")

    stmt = select(Record).where(Record.entity_id == entity_id, Record.is_deleted.is_(False))

    for filter_field, filter_expr in (node.get("filter") or {}).items():
        # Each filter value is itself resolved first — this is how a
        # chained lookup ("filter номенклатура by the material_id a
        # preceding lookup returned") falls out of the same recursion.
        resolved = (
            await resolve_lookups(filter_expr, db, ctx)
            if isinstance(filter_expr, dict)
            else filter_expr
        )
        filter_value = (
            resolved["value"]
            if isinstance(resolved, dict) and resolved.get("type") == "literal"
            else (evaluate(resolved, ctx.record) if isinstance(resolved, dict) else resolved)
        )
        if filter_value is None:
            # An unresolvable filter (e.g. the chained id wasn't found) means
            # this lookup can't match anything real — short-circuit to an
            # impossible condition rather than issuing a query that (with a
            # NULL comparison) would silently match nothing anyway.
            return 0 if agg in ("sum", "count") else None
        if filter_field == "id":
            try:
                stmt = stmt.where(Record.id == uuid.UUID(str(filter_value)))
            except ValueError as exc:
                raise RuleLookupError(f"filter.id is not a valid UUID: {filter_value!r}") from exc
        else:
            stmt = stmt.where(_jsonb_text(filter_field) == str(filter_value))

    stmt = stmt.limit(1001)  # sanity cap, same order of magnitude as other rule limits

    result = await db.execute(stmt)
    records = list(result.scalars().all())

    if agg == "value":
        return records[0].payload.get(field_name) if records else None
    if agg == "count":
        return len(records)

    numbers: list[float] = []
    for r in records:
        raw = r.payload.get(field_name)
        if raw is None:
            continue
        try:
            numbers.append(float(raw))
        except (TypeError, ValueError):
            continue

    if agg == "sum":
        return sum(numbers)
    if agg == "avg":
        return sum(numbers) / len(numbers) if numbers else None
    if agg == "min":
        return min(numbers) if numbers else None
    if agg == "max":
        return max(numbers) if numbers else None
    raise RuleError(f"Unknown lookup.agg: {agg!r}")


# Action types whose value is a single expression node (resolved the same
# way a condition's compare `value` is).
_ACTION_SINGLE_EXPR_KEYS = ("value",)
# Action types whose value is a {field_name: expression} dict — each entry
# resolved independently.
_ACTION_EXPR_DICT_KEYS = ("payload", "match", "increment")


def contains_lookup(node: Any) -> bool:
    """Cheap, DB-free scan for whether `node` (a conditions tree, a single
    action dict, or a list of either) contains any "lookup" subtree at all.
    Lets callers skip opening a DB session entirely for the (overwhelming)
    common case of rules that never use one."""
    if isinstance(node, list):
        return any(contains_lookup(item) for item in node)
    if not isinstance(node, dict):
        return False
    if node.get("type") == "lookup":
        return True
    for key in ("children", "args"):
        if contains_lookup(node.get(key, [])):
            return True
    for key in ("left", "right", "value"):
        if contains_lookup(node.get(key)):
            return True
    for key in _ACTION_EXPR_DICT_KEYS:
        if contains_lookup(list((node.get(key) or {}).values())):
            return True
    if contains_lookup(list((node.get("filter") or {}).values())):
        return True
    return False


async def _resolve_action_lookups(
    action: dict[str, Any], db: AsyncSession, ctx: ExecutionContext
) -> dict[str, Any]:
    """Resolve every "lookup" node reachable from one action dict — its
    single-expression fields (set_field.value) and its {field: expr} dicts
    (create_record.payload/match/increment, update_record.payload). Fields
    that aren't present, or aren't expression dicts (a plain literal), pass
    through unchanged."""
    new_action = dict(action)
    for key in _ACTION_SINGLE_EXPR_KEYS:
        if isinstance(action.get(key), dict):
            new_action[key] = await resolve_lookups(action[key], db, ctx)
    for key in _ACTION_EXPR_DICT_KEYS:
        sub = action.get(key)
        if isinstance(sub, dict):
            new_action[key] = {
                k: (await resolve_lookups(v, db, ctx) if isinstance(v, dict) else v)
                for k, v in sub.items()
            }
    return new_action


async def resolve_rule_lookups(
    conditions: dict[str, Any],
    actions: list[dict[str, Any]],
    db: AsyncSession,
    ctx: ExecutionContext,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Resolve every "lookup" node inside one automation rule's conditions
    and actions, before handing both to the pure interpreter. Mirrors what
    ValidationRuleService does for a validation rule's conditions, extended
    to actions — a "сумма операций по связанной записи"-style automation
    rule (ТЗ: write an aggregated value into a related table's record) needs
    its action's value resolved the same way a condition's does."""
    resolved_conditions = await resolve_lookups(conditions, db, ctx) if conditions else conditions
    resolved_actions = [await _resolve_action_lookups(a, db, ctx) for a in actions]
    return resolved_conditions, resolved_actions
