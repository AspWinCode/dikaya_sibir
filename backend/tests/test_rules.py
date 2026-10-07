"""
Rules Engine tests.

Unit tests: expressions, condition evaluation, action execution, graph/cycle detection.
Integration tests: rule CRUD, activate/deactivate, cycle check, dry-run, execution log.
"""

import uuid
from typing import Any

import pytest
from app.core.security import hash_password
from app.engine.expressions import ExpressionError, evaluate
from app.engine.graph import (
    RuleNode,
    build_dependency_graph,
    extract_rule_nodes,
    find_cycles,
)
from app.engine.interpreter import (
    ExecutionContext,
    RuleError,
    evaluate_conditions,
    execute_actions,
    run_rule,
    run_rules_batch,
)
from app.models.identity import Role, User, UserRole
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ==================================================================
# Helpers & fixtures
# ==================================================================


def _ctx(record: dict[str, Any] | None = None, event: str = "record.updated") -> ExecutionContext:
    return ExecutionContext(
        record=record or {},
        entity_id=uuid.uuid4(),
        app_id=uuid.uuid4(),
        event=event,
    )


@pytest.fixture()
async def builder(db_session: AsyncSession) -> User:
    for role_id in ("app_builder",):
        if not await db_session.get(Role, role_id):
            db_session.add(Role(id=role_id, display_name="App Builder", is_system=True))
    user = User(
        email="rules_builder@example.com",
        display_name="Rules Builder",
        password_hash=hash_password("Build1234!"),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id="app_builder"))
    await db_session.flush()
    return user


async def _login(client: AsyncClient, email: str, pwd: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _setup_app(client: AsyncClient, token: str) -> tuple[str, str]:
    """Create app + entity, return (app_id, entity_id)."""
    slug = f"rules-app-{uuid.uuid4().hex[:6]}"
    app_resp = await client.post(
        "/api/v1/apps",
        json={"slug": slug, "name": "Rules Test App"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert app_resp.status_code == 201, app_resp.text
    app_id = app_resp.json()["id"]

    ent_resp = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "order", "display_name": "Order"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ent_resp.status_code == 201, ent_resp.text
    entity_id = ent_resp.json()["id"]
    return app_id, entity_id


def _rule_body(entity_id: str, name: str = "Test Rule") -> dict[str, Any]:
    return {
        "entity_id": entity_id,
        "name": name,
        "trigger": {"event": "record.updated", "watch_fields": []},
        "conditions": {
            "type": "compare",
            "field": "status",
            "op": "eq",
            "value": "active",
        },
        "actions": [
            {"type": "set_field", "field": "flagged", "value": {"type": "literal", "value": True}},
        ],
        "priority": 100,
    }


# ==================================================================
# Unit: expressions.py
# ==================================================================


class TestLiteralExpr:
    def test_string(self) -> None:
        assert evaluate({"type": "literal", "value": "hello"}, {}) == "hello"

    def test_number(self) -> None:
        assert evaluate({"type": "literal", "value": 42}, {}) == 42

    def test_none(self) -> None:
        assert evaluate({"type": "literal", "value": None}, {}) is None

    def test_plain_value_passthrough(self) -> None:
        assert evaluate(99, {}) == 99


class TestFieldRefExpr:
    def test_existing_field(self) -> None:
        assert evaluate({"type": "field_ref", "field": "amount"}, {"amount": 150}) == 150

    def test_missing_field_returns_none(self) -> None:
        assert evaluate({"type": "field_ref", "field": "missing"}, {}) is None

    def test_non_string_field_raises(self) -> None:
        with pytest.raises(ExpressionError, match="must be a string"):
            evaluate({"type": "field_ref", "field": 123}, {})


class TestMathExpr:
    def _math(self, op: str, left: Any, right: Any) -> Any:
        return evaluate(
            {
                "type": "math",
                "op": op,
                "left": {"type": "literal", "value": left},
                "right": {"type": "literal", "value": right},
            },
            {},
        )

    def test_add(self) -> None:
        assert self._math("add", 3, 4) == 7.0

    def test_subtract(self) -> None:
        assert self._math("subtract", 10, 3) == 7.0

    def test_multiply(self) -> None:
        assert self._math("multiply", 6, 7) == 42.0

    def test_divide(self) -> None:
        assert self._math("divide", 10, 4) == 2.5

    def test_divide_by_zero(self) -> None:
        with pytest.raises(ExpressionError, match="Division by zero"):
            self._math("divide", 5, 0)

    def test_modulo(self) -> None:
        assert self._math("modulo", 10, 3) == 1.0

    def test_modulo_by_zero(self) -> None:
        with pytest.raises(ExpressionError, match="Modulo by zero"):
            self._math("modulo", 5, 0)

    def test_power(self) -> None:
        assert self._math("power", 2, 10) == 1024.0

    def test_unknown_op_raises(self) -> None:
        with pytest.raises(ExpressionError):
            self._math("sqrt", 9, 0)

    def test_non_numeric_operand(self) -> None:
        with pytest.raises(ExpressionError, match="is not a number"):
            self._math("add", "hello", 1)


class TestFuncExpr:
    def _call(self, name: str, *args: Any) -> Any:
        return evaluate(
            {
                "type": "func",
                "name": name,
                "args": [{"type": "literal", "value": a} for a in args],
            },
            {},
        )

    def test_upper(self) -> None:
        assert self._call("upper", "hello") == "HELLO"

    def test_lower(self) -> None:
        assert self._call("lower", "WORLD") == "world"

    def test_concat(self) -> None:
        assert self._call("concat", "foo", "bar", "baz") == "foobarbaz"

    def test_len_string(self) -> None:
        assert self._call("len", "hello") == 5

    def test_len_list(self) -> None:
        assert (
            evaluate(
                {"type": "func", "name": "len", "args": [{"type": "literal", "value": [1, 2, 3]}]},
                {},
            )
            == 3
        )

    def test_coalesce_returns_first_non_none(self) -> None:
        assert self._call("coalesce", None, None, "found") == "found"

    def test_coalesce_all_none(self) -> None:
        assert self._call("coalesce", None, None) is None

    def test_if_true(self) -> None:
        assert self._call("if", True, "yes", "no") == "yes"

    def test_if_false(self) -> None:
        assert self._call("if", False, "yes", "no") == "no"

    def test_if_no_else(self) -> None:
        assert self._call("if", False, "yes") is None

    def test_round(self) -> None:
        assert self._call("round", 3.14159, 2) == 3.14

    def test_abs_negative(self) -> None:
        assert self._call("abs", -7.5) == 7.5

    def test_now_returns_string(self) -> None:
        result = self._call("now")
        assert isinstance(result, str)
        assert "T" in result

    def test_today_returns_date_string(self) -> None:
        result = self._call("today")
        assert isinstance(result, str)
        assert len(result) == 10

    def test_unknown_func_raises(self) -> None:
        with pytest.raises(ExpressionError, match="Unknown function"):
            evaluate({"type": "func", "name": "os.system", "args": []}, {})


class TestExprDepthLimit:
    def test_exceeds_max_depth(self) -> None:
        def nest(depth: int) -> dict:
            if depth == 0:
                return {"type": "literal", "value": 1}
            return {
                "type": "math",
                "op": "add",
                "left": nest(depth - 1),
                "right": {"type": "literal", "value": 0},
            }

        with pytest.raises(ExpressionError, match="depth"):
            evaluate(nest(20), {})


# ==================================================================
# Unit: interpreter.py — condition evaluation
# ==================================================================


class TestConditionEvaluation:
    def test_empty_conditions_match(self) -> None:
        assert evaluate_conditions({}, _ctx()) is True

    def test_compare_eq_match(self) -> None:
        ctx = _ctx({"status": "active"})
        cond = {"type": "compare", "field": "status", "op": "eq", "value": "active"}
        assert evaluate_conditions(cond, ctx) is True

    def test_compare_eq_no_match(self) -> None:
        ctx = _ctx({"status": "inactive"})
        cond = {"type": "compare", "field": "status", "op": "eq", "value": "active"}
        assert evaluate_conditions(cond, ctx) is False

    def test_compare_ne(self) -> None:
        ctx = _ctx({"x": 1})
        assert evaluate_conditions({"type": "compare", "field": "x", "op": "ne", "value": 2}, ctx)

    def test_compare_gt(self) -> None:
        ctx = _ctx({"amount": 150})
        assert evaluate_conditions(
            {"type": "compare", "field": "amount", "op": "gt", "value": 100}, ctx
        )

    def test_compare_gte_equal(self) -> None:
        ctx = _ctx({"amount": 100})
        assert evaluate_conditions(
            {"type": "compare", "field": "amount", "op": "gte", "value": 100}, ctx
        )

    def test_compare_lt(self) -> None:
        ctx = _ctx({"amount": 50})
        assert evaluate_conditions(
            {"type": "compare", "field": "amount", "op": "lt", "value": 100}, ctx
        )

    def test_compare_lte(self) -> None:
        ctx = _ctx({"amount": 100})
        assert evaluate_conditions(
            {"type": "compare", "field": "amount", "op": "lte", "value": 100}, ctx
        )

    def test_compare_contains(self) -> None:
        ctx = _ctx({"title": "Invoice #001"})
        assert evaluate_conditions(
            {"type": "compare", "field": "title", "op": "contains", "value": "Invoice"}, ctx
        )

    def test_compare_icontains_case_insensitive(self) -> None:
        ctx = _ctx({"title": "Invoice #001"})
        assert evaluate_conditions(
            {"type": "compare", "field": "title", "op": "icontains", "value": "invoice"}, ctx
        )

    def test_compare_starts_with(self) -> None:
        ctx = _ctx({"name": "John Doe"})
        assert evaluate_conditions(
            {"type": "compare", "field": "name", "op": "starts_with", "value": "John"}, ctx
        )

    def test_compare_ends_with(self) -> None:
        ctx = _ctx({"name": "John Doe"})
        assert evaluate_conditions(
            {"type": "compare", "field": "name", "op": "ends_with", "value": "Doe"}, ctx
        )

    def test_compare_in(self) -> None:
        ctx = _ctx({"status": "paid"})
        assert evaluate_conditions(
            {"type": "compare", "field": "status", "op": "in", "value": ["draft", "paid"]}, ctx
        )

    def test_compare_nin(self) -> None:
        ctx = _ctx({"status": "draft"})
        assert evaluate_conditions(
            {"type": "compare", "field": "status", "op": "nin", "value": ["paid", "cancelled"]}, ctx
        )

    def test_compare_is_null(self) -> None:
        ctx = _ctx({"note": None})
        assert evaluate_conditions(
            {"type": "compare", "field": "note", "op": "is_null", "value": None}, ctx
        )

    def test_compare_is_not_null(self) -> None:
        ctx = _ctx({"note": "something"})
        assert evaluate_conditions(
            {"type": "compare", "field": "note", "op": "is_not_null", "value": None}, ctx
        )

    def test_and_all_true(self) -> None:
        ctx = _ctx({"a": 1, "b": 2})
        cond = {
            "type": "and",
            "children": [
                {"type": "compare", "field": "a", "op": "eq", "value": 1},
                {"type": "compare", "field": "b", "op": "eq", "value": 2},
            ],
        }
        assert evaluate_conditions(cond, ctx) is True

    def test_and_one_false(self) -> None:
        ctx = _ctx({"a": 1, "b": 99})
        cond = {
            "type": "and",
            "children": [
                {"type": "compare", "field": "a", "op": "eq", "value": 1},
                {"type": "compare", "field": "b", "op": "eq", "value": 2},
            ],
        }
        assert evaluate_conditions(cond, ctx) is False

    def test_or_one_true(self) -> None:
        ctx = _ctx({"status": "paid"})
        cond = {
            "type": "or",
            "children": [
                {"type": "compare", "field": "status", "op": "eq", "value": "draft"},
                {"type": "compare", "field": "status", "op": "eq", "value": "paid"},
            ],
        }
        assert evaluate_conditions(cond, ctx) is True

    def test_or_all_false(self) -> None:
        ctx = _ctx({"status": "cancelled"})
        cond = {
            "type": "or",
            "children": [
                {"type": "compare", "field": "status", "op": "eq", "value": "draft"},
                {"type": "compare", "field": "status", "op": "eq", "value": "paid"},
            ],
        }
        assert evaluate_conditions(cond, ctx) is False

    def test_not_inverts(self) -> None:
        ctx = _ctx({"status": "draft"})
        cond = {
            "type": "not",
            "children": [{"type": "compare", "field": "status", "op": "eq", "value": "active"}],
        }
        assert evaluate_conditions(cond, ctx) is True

    def test_not_empty_children_is_true(self) -> None:
        assert evaluate_conditions({"type": "not", "children": []}, _ctx()) is True

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(RuleError, match="Unknown condition type"):
            evaluate_conditions({"type": "unknown"}, _ctx())

    def test_value_as_expr_node(self) -> None:
        ctx = _ctx({"threshold": 100, "amount": 150})
        cond = {
            "type": "compare",
            "field": "amount",
            "op": "gt",
            "value": {"type": "field_ref", "field": "threshold"},
        }
        assert evaluate_conditions(cond, ctx) is True


# ==================================================================
# Unit: interpreter.py — action execution
# ==================================================================


class TestActionExecution:
    def test_set_field_literal(self) -> None:
        ctx = _ctx({"status": "draft"})
        result = execute_actions(
            [
                {
                    "type": "set_field",
                    "field": "status",
                    "value": {"type": "literal", "value": "active"},
                }
            ],
            ctx,
        )
        assert result.matched is True
        assert result.field_mutations["status"] == "active"

    def test_set_field_updates_ctx_for_downstream(self) -> None:
        ctx = _ctx({"amount": 100})
        execute_actions(
            [
                {
                    "type": "set_field",
                    "field": "doubled",
                    "value": {
                        "type": "math",
                        "op": "multiply",
                        "left": {"type": "field_ref", "field": "amount"},
                        "right": {"type": "literal", "value": 2},
                    },
                },
            ],
            ctx,
        )
        assert ctx.record["doubled"] == 200.0

    def test_set_field_missing_field_name(self) -> None:
        ctx = _ctx()
        result = execute_actions(
            [{"type": "set_field", "field": 123, "value": {"type": "literal", "value": "x"}}],
            ctx,
        )
        assert result.errors

    def test_create_record(self) -> None:
        eid = str(uuid.uuid4())
        ctx = _ctx({"name": "Alice"})
        result = execute_actions(
            [
                {
                    "type": "create_record",
                    "entity_id": eid,
                    "payload": {"copied_from": {"type": "field_ref", "field": "name"}},
                }
            ],
            ctx,
        )
        assert len(result.records_to_create) == 1
        assert result.records_to_create[0]["entity_id"] == eid
        assert result.records_to_create[0]["payload"]["copied_from"] == "Alice"

    def test_update_record(self) -> None:
        rec_id = str(uuid.uuid4())
        ctx = _ctx({"id": rec_id, "amount": 50})
        result = execute_actions(
            [
                {
                    "type": "update_record",
                    "record_id_field": "id",
                    "payload": {"amount": {"type": "literal", "value": 99}},
                }
            ],
            ctx,
        )
        assert len(result.records_to_update) == 1
        assert result.records_to_update[0]["record_id"] == rec_id
        assert result.records_to_update[0]["payload"]["amount"] == 99

    def test_update_record_missing_id_field(self) -> None:
        ctx = _ctx({"amount": 50})
        result = execute_actions(
            [{"type": "update_record", "record_id_field": "id", "payload": {}}],
            ctx,
        )
        assert result.errors

    def test_delete_record(self) -> None:
        rec_id = str(uuid.uuid4())
        ctx = _ctx({"id": rec_id})
        result = execute_actions(
            [{"type": "delete_record", "record_id_field": "id"}],
            ctx,
        )
        assert rec_id in result.records_to_delete

    def test_send_notification_to_field(self) -> None:
        ctx = _ctx({"email": "alice@example.com"})
        result = execute_actions(
            [
                {
                    "type": "send_notification",
                    "to_field": "email",
                    "subject": "Hello",
                    "template": "<p>Hi</p>",
                }
            ],
            ctx,
        )
        assert len(result.notifications) == 1
        assert result.notifications[0]["to"] == "alice@example.com"
        assert result.notifications[0]["subject"] == "Hello"

    def test_send_notification_static_to(self) -> None:
        ctx = _ctx()
        result = execute_actions(
            [{"type": "send_notification", "to": "admin@example.com", "subject": "Alert"}],
            ctx,
        )
        assert result.notifications[0]["to"] == "admin@example.com"

    def test_call_webhook(self) -> None:
        ctx = _ctx({"order_id": "123"})
        result = execute_actions(
            [
                {
                    "type": "call_webhook",
                    "url": "https://hook.example.com",
                    "method": "POST",
                    "payload": {"id": {"type": "field_ref", "field": "order_id"}},
                }
            ],
            ctx,
        )
        assert len(result.webhooks) == 1
        assert result.webhooks[0]["url"] == "https://hook.example.com"
        assert result.webhooks[0]["payload"]["id"] == "123"

    def test_stop_halts_remaining_actions(self) -> None:
        ctx = _ctx()
        result = execute_actions(
            [
                {"type": "stop"},
                {
                    "type": "set_field",
                    "field": "should_not_set",
                    "value": {"type": "literal", "value": True},
                },
            ],
            ctx,
        )
        assert result.stopped is True
        assert "should_not_set" not in result.field_mutations

    def test_unknown_action_type_logged_non_fatal(self) -> None:
        ctx = _ctx()
        result = execute_actions(
            [{"type": "explode"}],
            ctx,
        )
        assert result.errors
        assert result.matched is True

    def test_exceeds_max_actions(self) -> None:
        ctx = _ctx()
        actions = [
            {"type": "set_field", "field": f"f{i}", "value": {"type": "literal", "value": i}}
            for i in range(21)
        ]
        with pytest.raises(RuleError, match="maximum"):
            execute_actions(actions, ctx)


# ==================================================================
# Unit: interpreter.py — run_rule
# ==================================================================


class TestRunRule:
    def _trigger(
        self, event: str = "record.updated", watch_fields: list[str] | None = None
    ) -> dict:
        return {"event": event, "watch_fields": watch_fields or []}

    def _cond_always_true(self) -> dict:
        return {}

    def _action_set(self, field: str, value: Any) -> dict:
        return {"type": "set_field", "field": field, "value": {"type": "literal", "value": value}}

    def test_event_match_executes(self) -> None:
        ctx = _ctx(event="record.updated")
        result = run_rule(self._trigger("record.updated"), {}, [self._action_set("x", 1)], ctx)
        assert result.matched is True

    def test_event_mismatch_skips(self) -> None:
        ctx = _ctx(event="record.created")
        result = run_rule(self._trigger("record.deleted"), {}, [], ctx)
        assert result.matched is False

    def test_field_changed_is_subtype_of_record_updated(self) -> None:
        ctx = ExecutionContext(
            record={"amount": 100},
            entity_id=uuid.uuid4(),
            app_id=uuid.uuid4(),
            event="record.updated",
            changed_fields=["amount"],
        )
        result = run_rule(
            {"event": "field.changed", "watch_fields": ["amount"]},
            {},
            [self._action_set("triggered", True)],
            ctx,
        )
        assert result.matched is True

    def test_field_changed_watch_not_in_changed(self) -> None:
        ctx = ExecutionContext(
            record={"name": "Alice"},
            entity_id=uuid.uuid4(),
            app_id=uuid.uuid4(),
            event="record.updated",
            changed_fields=["name"],
        )
        result = run_rule(
            {"event": "field.changed", "watch_fields": ["amount"]},
            {},
            [],
            ctx,
        )
        assert result.matched is False

    def test_conditions_false_skips_actions(self) -> None:
        ctx = _ctx({"status": "draft"})
        cond = {"type": "compare", "field": "status", "op": "eq", "value": "active"}
        result = run_rule(self._trigger(), cond, [self._action_set("x", 1)], ctx)
        assert result.matched is False
        assert result.field_mutations == {}

    def test_conditions_true_executes_actions(self) -> None:
        ctx = _ctx({"status": "active"})
        cond = {"type": "compare", "field": "status", "op": "eq", "value": "active"}
        result = run_rule(self._trigger(), cond, [self._action_set("flagged", True)], ctx)
        assert result.matched is True
        assert result.field_mutations["flagged"] is True

    def test_empty_trigger_event_matches_all(self) -> None:
        ctx = _ctx(event="record.created")
        result = run_rule({}, {}, [self._action_set("x", 1)], ctx)
        assert result.matched is True


# ==================================================================
# Unit: run_rules_batch — priority-based conflict resolution (ТЗ 3.5.4)
# ==================================================================


class TestRunRulesBatch:
    def _rule(
        self,
        rule_id: str,
        priority: int,
        field: str,
        value: Any,
        condition: dict | None = None,
    ) -> dict:
        return {
            "id": rule_id,
            "trigger": {"event": "record.updated", "watch_fields": []},
            "conditions": condition or {},
            "actions": [
                {"type": "set_field", "field": field, "value": {"type": "literal", "value": value}},
            ],
            "priority": priority,
        }

    def test_no_conflict_different_fields(self) -> None:
        ctx = _ctx({})
        rules = [
            self._rule("r1", 1, "a", "x"),
            self._rule("r2", 2, "b", "y"),
        ]
        batch = run_rules_batch(rules, ctx)
        assert batch.applied_mutations == {"a": "x", "b": "y"}
        assert batch.conflicts == []

    def test_higher_priority_wins_on_conflict(self) -> None:
        """Lower priority number = runs first = wins (ТЗ 3.5.4)."""
        ctx = _ctx({})
        rules = [
            self._rule("high", 1, "status", "approved"),
            self._rule("low", 50, "status", "rejected"),
        ]
        batch = run_rules_batch(rules, ctx)
        assert batch.applied_mutations == {"status": "approved"}
        assert ctx.record["status"] == "approved"  # not left as the loser's value

    def test_conflict_is_recorded_with_winner_and_loser(self) -> None:
        ctx = _ctx({})
        rules = [
            self._rule("high", 1, "status", "approved"),
            self._rule("low", 50, "status", "rejected"),
        ]
        batch = run_rules_batch(rules, ctx)
        assert len(batch.conflicts) == 1
        conflict = batch.conflicts[0]
        assert conflict.field_name == "status"
        assert conflict.winning_rule_id == "high"
        assert conflict.winning_value == "approved"
        assert conflict.losing_writes == [{"rule_id": "low", "value": "rejected"}]

    def test_identical_values_are_not_a_conflict(self) -> None:
        ctx = _ctx({})
        rules = [
            self._rule("r1", 1, "status", "approved"),
            self._rule("r2", 50, "status", "approved"),
        ]
        batch = run_rules_batch(rules, ctx)
        assert batch.conflicts == []
        assert batch.applied_mutations == {"status": "approved"}

    def test_order_in_input_list_determines_winner_not_numeric_priority_value(self) -> None:
        """run_rules_batch trusts caller-provided order (RuleService sorts by
        priority before calling) — it does not re-sort by the priority field
        itself, so a caller bug in sorting would surface here, not be masked."""
        ctx = _ctx({})
        rules = [
            self._rule("first", 999, "status", "A"),  # listed first despite high priority number
            self._rule("second", 1, "status", "B"),
        ]
        batch = run_rules_batch(rules, ctx)
        assert batch.applied_mutations == {"status": "A"}
        assert batch.conflicts[0].winning_rule_id == "first"

    def test_three_way_conflict_lists_every_loser(self) -> None:
        ctx = _ctx({})
        rules = [
            self._rule("r1", 1, "status", "A"),
            self._rule("r2", 2, "status", "B"),
            self._rule("r3", 3, "status", "C"),
        ]
        batch = run_rules_batch(rules, ctx)
        assert len(batch.conflicts) == 1
        conflict = batch.conflicts[0]
        assert conflict.winning_rule_id == "r1"
        assert conflict.losing_writes == [
            {"rule_id": "r2", "value": "B"},
            {"rule_id": "r3", "value": "C"},
        ]

    def test_downstream_rule_condition_sees_winning_value(self) -> None:
        """A later rule's condition must evaluate against the WINNING value of
        an earlier conflict, not whatever the losing rule tried to write."""
        ctx = _ctx({})
        rules = [
            self._rule("setter_high", 1, "status", "approved"),
            self._rule("setter_low", 50, "status", "rejected"),
            self._rule(
                "watcher",
                60,
                "notified",
                True,
                condition={"type": "compare", "field": "status", "op": "eq", "value": "approved"},
            ),
        ]
        batch = run_rules_batch(rules, ctx)
        assert batch.applied_mutations["notified"] is True

    def test_unmatched_rule_contributes_nothing(self) -> None:
        ctx = _ctx({"status": "draft"})
        rules = [
            self._rule(
                "r1",
                1,
                "x",
                1,
                condition={"type": "compare", "field": "status", "op": "eq", "value": "active"},
            ),
        ]
        batch = run_rules_batch(rules, ctx)
        assert batch.applied_mutations == {}
        assert batch.outcomes[0].result.matched is False

    def test_outcome_tracks_overridden_fields_for_the_losing_rule(self) -> None:
        ctx = _ctx({})
        rules = [
            self._rule("high", 1, "status", "approved"),
            self._rule("low", 50, "status", "rejected"),
        ]
        batch = run_rules_batch(rules, ctx)
        outcomes_by_id = {o.rule_id: o for o in batch.outcomes}
        assert outcomes_by_id["high"].overridden_fields == []
        assert outcomes_by_id["low"].overridden_fields == ["status"]

    def test_non_field_actions_accumulate_across_all_matched_rules(self) -> None:
        ctx = _ctx({})
        rules = [
            {
                "id": "r1",
                "priority": 1,
                "trigger": {"event": "record.updated", "watch_fields": []},
                "conditions": {},
                "actions": [{"type": "create_record", "entity_id": "e1", "payload": {}}],
            },
            {
                "id": "r2",
                "priority": 2,
                "trigger": {"event": "record.updated", "watch_fields": []},
                "conditions": {},
                "actions": [{"type": "create_record", "entity_id": "e2", "payload": {}}],
            },
        ]
        batch = run_rules_batch(rules, ctx)
        assert len(batch.records_to_create) == 2


# ==================================================================
# Unit: graph.py — dependency graph + cycle detection
# ==================================================================


class TestDependencyGraph:
    def _node(
        self,
        rule_id: str,
        entity_id: str,
        trigger_event: str = "record.updated",
        action_entity_ids: list[str] | None = None,
    ) -> RuleNode:
        return RuleNode(
            rule_id=rule_id,
            entity_id=entity_id,
            trigger_event=trigger_event,
            trigger_fields=[],
            action_entity_ids=action_entity_ids or [],
            action_events=[],
        )

    def test_no_rules_empty_graph(self) -> None:
        assert build_dependency_graph([]) == {}

    def test_single_rule_no_deps(self) -> None:
        nodes = [self._node("r1", "e1")]
        graph = build_dependency_graph(nodes)
        assert graph == {"r1": []}

    def test_r1_writes_entity_r2_listens(self) -> None:
        nodes = [
            self._node("r1", "e1", action_entity_ids=["e2"]),
            self._node("r2", "e2"),
        ]
        graph = build_dependency_graph(nodes)
        assert "r2" in graph["r1"]
        assert graph["r2"] == []

    def test_no_self_dependency_via_graph(self) -> None:
        nodes = [self._node("r1", "e1", action_entity_ids=["e1"])]
        graph = build_dependency_graph(nodes)
        assert "r1" not in graph["r1"]


class TestTarjanSCC:
    def test_no_cycle(self) -> None:
        graph = {"a": ["b"], "b": ["c"], "c": []}
        cycles = find_cycles(graph)
        assert cycles == []

    def test_two_node_cycle(self) -> None:
        graph = {"a": ["b"], "b": ["a"]}
        cycles = find_cycles(graph)
        assert len(cycles) == 1
        assert set(cycles[0]) == {"a", "b"}

    def test_three_node_cycle(self) -> None:
        graph = {"a": ["b"], "b": ["c"], "c": ["a"]}
        cycles = find_cycles(graph)
        assert len(cycles) == 1
        assert set(cycles[0]) == {"a", "b", "c"}

    def test_self_loop(self) -> None:
        graph = {"a": ["a"], "b": []}
        cycles = find_cycles(graph)
        assert len(cycles) == 1
        assert cycles[0] == ["a"]

    def test_no_cycle_with_convergence(self) -> None:
        # Diamond: a→b, a→c, b→d, c→d — no cycle
        graph = {"a": ["b", "c"], "b": ["d"], "c": ["d"], "d": []}
        cycles = find_cycles(graph)
        assert cycles == []

    def test_disconnected_with_one_cycle(self) -> None:
        graph = {"x": ["y"], "y": ["x"], "z": []}
        cycles = find_cycles(graph)
        assert len(cycles) == 1
        assert set(cycles[0]) == {"x", "y"}


class TestExtractRuleNodes:
    def test_basic_extraction(self) -> None:
        eid = str(uuid.uuid4())
        rid = str(uuid.uuid4())
        rules_raw = [
            {
                "id": rid,
                "entity_id": eid,
                "trigger": {"event": "record.updated", "watch_fields": ["amount"]},
                "actions": [{"type": "create_record", "entity_id": eid}],
            }
        ]
        nodes = extract_rule_nodes(rules_raw)
        assert len(nodes) == 1
        assert nodes[0].rule_id == rid
        assert nodes[0].entity_id == eid
        assert nodes[0].trigger_fields == ["amount"]
        assert eid in nodes[0].action_entity_ids

    def test_update_delete_action_entity_id(self) -> None:
        eid = str(uuid.uuid4())
        rid = str(uuid.uuid4())
        rules_raw = [
            {
                "id": rid,
                "entity_id": eid,
                "trigger": {"event": "record.updated"},
                "actions": [{"type": "update_record"}],
            }
        ]
        nodes = extract_rule_nodes(rules_raw)
        assert eid in nodes[0].action_entity_ids


# ==================================================================
# Integration tests: rule CRUD + endpoints
# ==================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_rule(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"/api/v1/apps/{app_id}/rules",
        json=_rule_body(entity_id),
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Rule"
    assert data["is_active"] is False
    assert data["version"] == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_rule_persists_the_requested_rule_type(
    client: AsyncClient, builder: User
) -> None:
    """create_rule used to build the ORM Rule without passing rule_type at
    all, so every rule silently fell back to the column's "automation"
    default regardless of what was requested — a validation rule's
    block_save action and lookup conditions would then get dispatched to
    the async automation interpreter (which understands neither) instead
    of ValidationRuleService's synchronous pre-commit check, and an
    autofill rule would run async instead of inline. Round-trip through
    the real create + get endpoints, not just the Pydantic schema."""
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    for rule_type in ("validation", "autofill", "automation"):
        body = _rule_body(entity_id, name=f"Rule {rule_type}")
        body["rule_type"] = rule_type
        if rule_type == "validation":
            body["actions"] = [{"type": "block_save", "message": "blocked"}]
        create = await client.post(f"/api/v1/apps/{app_id}/rules", json=body, headers=headers)
        assert create.status_code == 201, create.text
        assert create.json()["rule_type"] == rule_type

        fetched = await client.get(
            f"/api/v1/apps/{app_id}/rules/{create.json()['id']}", headers=headers
        )
        assert fetched.json()["rule_type"] == rule_type


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_rule_can_change_rule_type(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        f"/api/v1/apps/{app_id}/rules", json=_rule_body(entity_id), headers=headers
    )
    rule_id = create.json()["id"]
    assert create.json()["rule_type"] == "automation"

    update = await client.patch(
        f"/api/v1/apps/{app_id}/rules/{rule_id}",
        json={"rule_type": "autofill"},
        headers=headers,
    )
    assert update.status_code == 200, update.text
    assert update.json()["rule_type"] == "autofill"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_rule(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        f"/api/v1/apps/{app_id}/rules", json=_rule_body(entity_id), headers=headers
    )
    rule_id = create.json()["id"]

    resp = await client.get(f"/api/v1/apps/{app_id}/rules/{rule_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == rule_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_rule_not_found(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, _ = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"/api/v1/apps/{app_id}/rules/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_rules_empty(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, _ = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"/api/v1/apps/{app_id}/rules", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_rules_active_only(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/apps/{app_id}/rules"

    r1 = await client.post(base, json=_rule_body(entity_id, "Rule A"), headers=headers)
    r2 = await client.post(base, json=_rule_body(entity_id, "Rule B"), headers=headers)
    await client.post(f"{base}/{r1.json()['id']}/activate", headers=headers)

    all_resp = await client.get(base, headers=headers)
    assert len(all_resp.json()) == 2

    active_resp = await client.get(f"{base}?active_only=true", headers=headers)
    assert len(active_resp.json()) == 1
    assert active_resp.json()[0]["id"] == r1.json()["id"]

    _ = r2  # r2 intentionally kept inactive


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_rule(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        f"/api/v1/apps/{app_id}/rules", json=_rule_body(entity_id), headers=headers
    )
    rule_id = create.json()["id"]

    resp = await client.patch(
        f"/api/v1/apps/{app_id}/rules/{rule_id}",
        json={"name": "Renamed Rule", "priority": 50},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed Rule"
    assert resp.json()["priority"] == 50
    assert resp.json()["version"] == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_rule(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        f"/api/v1/apps/{app_id}/rules", json=_rule_body(entity_id), headers=headers
    )
    rule_id = create.json()["id"]

    del_resp = await client.delete(f"/api/v1/apps/{app_id}/rules/{rule_id}", headers=headers)
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/apps/{app_id}/rules/{rule_id}", headers=headers)
    assert get_resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_activate_and_deactivate_rule(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        f"/api/v1/apps/{app_id}/rules", json=_rule_body(entity_id), headers=headers
    )
    rule_id = create.json()["id"]

    activate = await client.post(f"/api/v1/apps/{app_id}/rules/{rule_id}/activate", headers=headers)
    assert activate.status_code == 200
    assert activate.json()["is_active"] is True

    deactivate = await client.post(
        f"/api/v1/apps/{app_id}/rules/{rule_id}/deactivate", headers=headers
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["is_active"] is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dry_run_test_endpoint_matched(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        f"/api/v1/apps/{app_id}/rules", json=_rule_body(entity_id), headers=headers
    )
    rule_id = create.json()["id"]

    test_resp = await client.post(
        f"/api/v1/apps/{app_id}/rules/{rule_id}/test",
        json={"record_payload": {"status": "active"}, "event": "record.updated"},
        headers=headers,
    )
    assert test_resp.status_code == 200
    data = test_resp.json()
    assert data["matched"] is True
    assert data["field_mutations"]["flagged"] is True
    assert data["errors"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dry_run_test_endpoint_not_matched(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        f"/api/v1/apps/{app_id}/rules", json=_rule_body(entity_id), headers=headers
    )
    rule_id = create.json()["id"]

    test_resp = await client.post(
        f"/api/v1/apps/{app_id}/rules/{rule_id}/test",
        json={"record_payload": {"status": "draft"}, "event": "record.updated"},
        headers=headers,
    )
    assert test_resp.status_code == 200
    assert test_resp.json()["matched"] is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cycles_endpoint_no_cycles(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, _ = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"/api/v1/apps/{app_id}/rules/cycles", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["has_cycles"] is False
    assert resp.json()["cycles"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execution_log_endpoint(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        f"/api/v1/apps/{app_id}/rules", json=_rule_body(entity_id), headers=headers
    )
    rule_id = create.json()["id"]

    # No logs yet — should return empty list
    resp = await client.get(f"/api/v1/apps/{app_id}/rules/{rule_id}/logs", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rule_create_validates_action_type(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    body = _rule_body(entity_id)
    body["actions"] = [{"type": "do_something_evil"}]

    resp = await client.post(f"/api/v1/apps/{app_id}/rules", json=body, headers=headers)
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rule_create_validates_condition_depth(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    def deep_and(depth: int) -> dict:
        if depth == 0:
            return {"type": "compare", "field": "x", "op": "eq", "value": 1}
        return {"type": "and", "children": [deep_and(depth - 1)]}

    body = _rule_body(entity_id)
    body["conditions"] = deep_and(25)

    resp = await client.post(f"/api/v1/apps/{app_id}/rules", json=body, headers=headers)
    assert resp.status_code == 422


# ==================================================================
# Process steps — unit (pure conversion) + integration (CRUD/reorder)
# ==================================================================

from app.schemas.rules import (  # noqa: E402
    ProcessStepCreate,
    ensure_step_ids,
    node_to_step,
    step_to_node,
)


class TestStepConversion:
    def test_step_to_node_flattens_config_and_adds_id(self) -> None:
        node = step_to_node("set_field", {"field": "x", "value": 1})
        assert node["type"] == "set_field"
        assert node["field"] == "x" and node["value"] == 1
        assert node["id"]  # generated

    def test_step_to_node_keeps_explicit_id_and_strips_reserved(self) -> None:
        node = step_to_node("stop", {"id": "ignored", "type": "ignored"}, step_id="s1")
        assert node["id"] == "s1" and node["type"] == "stop"

    def test_node_to_step_projects_config_and_order(self) -> None:
        step = node_to_step({"id": "s1", "type": "set_field", "field": "x", "value": 1}, 3)
        assert step.id == "s1" and step.order == 3 and step.type == "set_field"
        assert step.config == {"field": "x", "value": 1}

    def test_ensure_step_ids_backfills_missing(self) -> None:
        actions = [{"type": "stop"}, {"id": "keep", "type": "set_field", "field": "a", "value": 1}]
        out, changed = ensure_step_ids(actions)
        assert changed is True
        assert out[0]["id"] and out[1]["id"] == "keep"

    def test_step_create_rejects_invalid_type(self) -> None:
        with pytest.raises(ValueError):
            ProcessStepCreate(type="not_a_real_action", config={})


async def _create_rule(client: AsyncClient, app_id: str, entity_id: str, headers: dict) -> str:
    resp = await client.post(
        f"/api/v1/apps/{app_id}/rules", json=_rule_body(entity_id), headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_steps_returns_existing_actions(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    rule_id = await _create_rule(client, app_id, entity_id, headers)

    resp = await client.get(f"/api/v1/apps/{app_id}/rules/{rule_id}/steps", headers=headers)
    assert resp.status_code == 200, resp.text
    steps = resp.json()
    assert len(steps) == 1
    assert steps[0]["type"] == "set_field"
    assert steps[0]["order"] == 0
    assert steps[0]["id"]  # backfilled
    assert steps[0]["config"]["field"] == "flagged"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_add_update_delete_step(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    rule_id = await _create_rule(client, app_id, entity_id, headers)

    # add
    add = await client.post(
        f"/api/v1/apps/{app_id}/rules/{rule_id}/steps",
        json={"type": "send_notification", "config": {"to": "a@b.c", "subject": "Hi"}},
        headers=headers,
    )
    assert add.status_code == 201, add.text
    step = add.json()
    assert step["type"] == "send_notification" and step["order"] == 1
    step_id = step["id"]

    # update
    upd = await client.patch(
        f"/api/v1/apps/{app_id}/rules/{rule_id}/steps/{step_id}",
        json={"config": {"to": "x@y.z", "subject": "Bye"}},
        headers=headers,
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["config"]["subject"] == "Bye"

    # delete
    dele = await client.delete(
        f"/api/v1/apps/{app_id}/rules/{rule_id}/steps/{step_id}", headers=headers
    )
    assert dele.status_code == 204
    after = await client.get(f"/api/v1/apps/{app_id}/rules/{rule_id}/steps", headers=headers)
    assert len(after.json()) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_add_step_invalid_type_rejected(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    rule_id = await _create_rule(client, app_id, entity_id, headers)

    resp = await client.post(
        f"/api/v1/apps/{app_id}/rules/{rule_id}/steps",
        json={"type": "definitely_invalid", "config": {}},
        headers=headers,
    )
    assert resp.status_code == 422  # schema validator rejects before service


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reorder_steps(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    rule_id = await _create_rule(client, app_id, entity_id, headers)

    await client.post(
        f"/api/v1/apps/{app_id}/rules/{rule_id}/steps",
        json={"type": "stop", "config": {}},
        headers=headers,
    )
    steps = (
        await client.get(f"/api/v1/apps/{app_id}/rules/{rule_id}/steps", headers=headers)
    ).json()
    ids = [s["id"] for s in steps]
    reversed_ids = list(reversed(ids))

    resp = await client.put(
        f"/api/v1/apps/{app_id}/rules/{rule_id}/steps/reorder",
        json={"step_ids": reversed_ids},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert [s["id"] for s in resp.json()] == reversed_ids
    assert [s["order"] for s in resp.json()] == [0, 1]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_missing_step_404(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    rule_id = await _create_rule(client, app_id, entity_id, headers)

    resp = await client.patch(
        f"/api/v1/apps/{app_id}/rules/{rule_id}/steps/nonexistent",
        json={"config": {}},
        headers=headers,
    )
    assert resp.status_code == 404
