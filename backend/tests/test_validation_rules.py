"""Validation rules (rule_type="validation") — the "проверка достаточности
материалов по рецепту" feature: schema/AST validation and the pure
tree-walking part of the lookup resolver (no DB — those cases never reach
the branch that queries the database, so they're real, not mocked)."""

import uuid

import pytest
from app.engine.interpreter import ExecutionContext
from app.engine.lookup import resolve_lookups
from app.schemas.rules import RuleCreate, RuleTrigger, TriggerEvent
from pydantic import ValidationError


def _rule(conditions: dict, actions: list[dict]) -> dict:
    return {
        "entity_id": uuid.uuid4(),
        "name": "test",
        "rule_type": "validation",
        "trigger": RuleTrigger(event=TriggerEvent.RECORD_CREATED),
        "conditions": conditions,
        "actions": actions,
    }


class TestBlockSaveActionValidation:
    def test_block_save_accepted(self) -> None:
        RuleCreate(**_rule({}, [{"type": "block_save", "message": "Недостаточно материала"}]))

    def test_block_save_default_message(self) -> None:
        rc = RuleCreate(**_rule({}, [{"type": "block_save"}]))
        assert rc.actions == [{"type": "block_save"}]  # stored as raw dict, default applied on read

    def test_unknown_action_still_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RuleCreate(**_rule({}, [{"type": "nonexistent_action"}]))


class TestLookupExprValidation:
    def test_simple_lookup_in_compare_value_accepted(self) -> None:
        cond = {
            "type": "compare",
            "field": "qty_completed",
            "op": "lte",
            "value": {
                "type": "lookup",
                "entity_id": str(uuid.uuid4()),
                "filter": {"material_id": {"type": "field_ref", "field": "material_id"}},
                "field": "available_qty",
                "agg": "value",
            },
        }
        RuleCreate(**_rule(cond, [{"type": "block_save", "message": "not enough stock"}]))

    def test_lookup_missing_entity_id_rejected(self) -> None:
        cond = {
            "type": "compare",
            "field": "x",
            "op": "eq",
            "value": {"type": "lookup", "agg": "value", "field": "y"},
        }
        with pytest.raises(ValidationError):
            RuleCreate(**_rule(cond, [{"type": "block_save"}]))

    def test_lookup_invalid_agg_rejected(self) -> None:
        cond = {
            "type": "compare",
            "field": "x",
            "op": "eq",
            "value": {
                "type": "lookup",
                "entity_id": str(uuid.uuid4()),
                "field": "y",
                "agg": "median",
            },
        }
        with pytest.raises(ValidationError):
            RuleCreate(**_rule(cond, [{"type": "block_save"}]))

    def test_lookup_count_agg_does_not_require_field(self) -> None:
        cond = {
            "type": "compare",
            "field": "x",
            "op": "gt",
            "value": {"type": "lookup", "entity_id": str(uuid.uuid4()), "agg": "count"},
        }
        RuleCreate(**_rule(cond, [{"type": "block_save"}]))

    def test_lookup_non_count_agg_requires_field(self) -> None:
        cond = {
            "type": "compare",
            "field": "x",
            "op": "gt",
            "value": {"type": "lookup", "entity_id": str(uuid.uuid4()), "agg": "sum"},
        }
        with pytest.raises(ValidationError):
            RuleCreate(**_rule(cond, [{"type": "block_save"}]))

    def test_nested_lookup_in_filter_accepted(self) -> None:
        """The chained scenario: filter номенклатура by an id that is itself
        the result of a lookup into рецепты."""
        inner_lookup = {
            "type": "lookup",
            "entity_id": str(uuid.uuid4()),
            "filter": {"operation_id": {"type": "field_ref", "field": "operation_id"}},
            "field": "material_id",
            "agg": "value",
        }
        outer_lookup = {
            "type": "lookup",
            "entity_id": str(uuid.uuid4()),
            "filter": {"id": inner_lookup},
            "field": "available_qty",
            "agg": "value",
        }
        cond = {"type": "compare", "field": "qty_completed", "op": "lte", "value": outer_lookup}
        RuleCreate(**_rule(cond, [{"type": "block_save"}]))

    def test_unknown_expr_type_inside_lookup_filter_rejected(self) -> None:
        cond = {
            "type": "compare",
            "field": "x",
            "op": "eq",
            "value": {
                "type": "lookup",
                "entity_id": str(uuid.uuid4()),
                "field": "y",
                "agg": "value",
                "filter": {"z": {"type": "bogus"}},
            },
        }
        with pytest.raises(ValidationError):
            RuleCreate(**_rule(cond, [{"type": "block_save"}]))


class TestResolveLookupsTreeWalk:
    """The recursive tree-walk in app.engine.lookup.resolve_lookups — cases
    that never reach a "lookup" node never touch the DB, so a dummy db
    object (never actually called) proves the recursion is correct."""

    @pytest.mark.asyncio
    async def test_literal_passthrough(self) -> None:
        ctx = ExecutionContext(
            record={}, entity_id=uuid.uuid4(), app_id=uuid.uuid4(), event="record.created"
        )
        node = {"type": "literal", "value": 42}
        result = await resolve_lookups(node, db=None, ctx=ctx)  # type: ignore[arg-type]
        assert result == node

    @pytest.mark.asyncio
    async def test_field_ref_passthrough(self) -> None:
        ctx = ExecutionContext(
            record={}, entity_id=uuid.uuid4(), app_id=uuid.uuid4(), event="record.created"
        )
        node = {"type": "field_ref", "field": "qty"}
        result = await resolve_lookups(node, db=None, ctx=ctx)  # type: ignore[arg-type]
        assert result == node

    @pytest.mark.asyncio
    async def test_raw_python_value_passthrough(self) -> None:
        ctx = ExecutionContext(
            record={}, entity_id=uuid.uuid4(), app_id=uuid.uuid4(), event="record.created"
        )
        assert await resolve_lookups(5, db=None, ctx=ctx) == 5  # type: ignore[arg-type]
        assert await resolve_lookups("x", db=None, ctx=ctx) == "x"  # type: ignore[arg-type]
        assert await resolve_lookups(None, db=None, ctx=ctx) is None  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_and_or_not_recurse_into_children(self) -> None:
        ctx = ExecutionContext(
            record={}, entity_id=uuid.uuid4(), app_id=uuid.uuid4(), event="record.created"
        )
        node = {
            "type": "and",
            "children": [
                {"type": "compare", "field": "a", "op": "eq", "value": 1},
                {
                    "type": "not",
                    "children": [{"type": "compare", "field": "b", "op": "eq", "value": 2}],
                },
            ],
        }
        result = await resolve_lookups(node, db=None, ctx=ctx)  # type: ignore[arg-type]
        assert result == node  # nothing to resolve, structurally identical

    @pytest.mark.asyncio
    async def test_math_recurses_into_left_and_right(self) -> None:
        ctx = ExecutionContext(
            record={}, entity_id=uuid.uuid4(), app_id=uuid.uuid4(), event="record.created"
        )
        node = {
            "type": "math",
            "op": "multiply",
            "left": {"type": "field_ref", "field": "qty"},
            "right": {"type": "literal", "value": 3},
        }
        result = await resolve_lookups(node, db=None, ctx=ctx)  # type: ignore[arg-type]
        assert result == node

    @pytest.mark.asyncio
    async def test_func_recurses_into_args(self) -> None:
        ctx = ExecutionContext(
            record={}, entity_id=uuid.uuid4(), app_id=uuid.uuid4(), event="record.created"
        )
        node = {
            "type": "func",
            "name": "round",
            "args": [{"type": "field_ref", "field": "x"}, {"type": "literal", "value": 2}],
        }
        result = await resolve_lookups(node, db=None, ctx=ctx)  # type: ignore[arg-type]
        assert result == node

    @pytest.mark.asyncio
    async def test_compare_without_dict_value_untouched(self) -> None:
        """A plain literal `value` (not an expression dict) is left as-is —
        only a dict `value` is recursed into."""
        ctx = ExecutionContext(
            record={}, entity_id=uuid.uuid4(), app_id=uuid.uuid4(), event="record.created"
        )
        node = {"type": "compare", "field": "x", "op": "eq", "value": 5}
        result = await resolve_lookups(node, db=None, ctx=ctx)  # type: ignore[arg-type]
        assert result == node
