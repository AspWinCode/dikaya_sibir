"""
Rules Engine wiring tests.

Verifies that POST/PATCH /records dispatch rule evaluation to the sandbox queue.
Celery `apply_async` is mocked so no actual worker or Redis is required.
"""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.identity import Role, User, UserRole
from app.services.rules import RuleService


# ------------------------------------------------------------------
# Shared fixtures
# ------------------------------------------------------------------


@pytest.fixture()
async def builder(db_session: AsyncSession) -> User:
    for role_id in ("app_builder",):
        if not await db_session.get(Role, role_id):
            db_session.add(Role(id=role_id, display_name="App Builder", is_system=True))
    user = User(
        email="wiring_builder@example.com",
        display_name="Wiring Builder",
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


async def _setup_entity(client: AsyncClient, token: str) -> tuple[str, str]:
    slug = f"wire-app-{uuid.uuid4().hex[:6]}"
    app = await client.post(
        "/api/v1/apps", json={"slug": slug, "name": "Wiring Test App"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert app.status_code == 201, app.text
    app_id = app.json()["id"]

    entity = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "orders", "display_name": "Orders"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert entity.status_code == 201, entity.text
    return app_id, entity.json()["id"]


def _rule_payload(entity_id: str, trigger_event: str = "record.created") -> dict[str, Any]:
    return {
        "entity_id": entity_id,
        "name": f"Auto-flag on {trigger_event}",
        "trigger": {"event": trigger_event, "watch_fields": []},
        "conditions": {},
        "actions": [
            {"type": "set_field", "field": "flagged", "value": {"type": "literal", "value": True}},
        ],
        "priority": 10,
    }


# ------------------------------------------------------------------
# Unit: evaluate_rules_for_event dispatches Celery tasks
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_rules_dispatches_to_sandbox(db_session: AsyncSession) -> None:
    """No active rules — nothing is dispatched."""
    app_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    record_id = uuid.uuid4()
    payload = {"amount": 100}

    mock_task = MagicMock()
    mock_task.id = "mock-task-id"

    with patch(
        "app.worker.tasks.sandbox.execute_rules_batch.apply_async",
        return_value=mock_task,
    ) as mock_apply:
        svc = RuleService(db_session)
        task_id = await svc.evaluate_rules_for_event(
            app_id, entity_id, record_id, payload, "record.created"
        )
        assert task_id is None
        mock_apply.assert_not_called()


@pytest.mark.asyncio
async def test_evaluate_rules_context_includes_record_id(db_session: AsyncSession) -> None:
    """Context passed to Celery includes record_id so sandbox can update the right row."""
    from app.models.logic import Rule

    app_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    record_id = uuid.uuid4()
    payload = {"status": "pending"}

    # Insert an active rule directly
    rule = Rule(
        app_id=app_id,
        entity_id=entity_id,
        name="Test wiring rule",
        trigger={"event": "record.created", "watch_fields": []},
        conditions={},
        actions=[{"type": "set_field", "field": "x", "value": {"type": "literal", "value": 1}}],
        priority=1,
        is_active=True,
    )
    db_session.add(rule)
    await db_session.flush()

    mock_task = MagicMock()
    mock_task.id = "mock-task-id"

    with patch(
        "app.worker.tasks.sandbox.execute_rules_batch.apply_async",
        return_value=mock_task,
    ) as mock_apply:
        svc = RuleService(db_session)
        task_id = await svc.evaluate_rules_for_event(
            app_id, entity_id, record_id, payload, "record.created"
        )
        assert task_id == "mock-task-id"
        called_kwargs = mock_apply.call_args.kwargs["kwargs"]
        assert called_kwargs["context"]["record_id"] == str(record_id)
        assert called_kwargs["context"]["entity_id"] == str(entity_id)
        assert called_kwargs["context"]["app_id"] == str(app_id)
        assert called_kwargs["context"]["event"] == "record.created"
        assert called_kwargs["context"]["record"] == payload
        assert len(called_kwargs["rules"]) == 1
        assert called_kwargs["rules"][0]["id"] == str(rule.id)


@pytest.mark.asyncio
async def test_validation_rules_are_never_dispatched_to_the_async_batch(db_session: AsyncSession) -> None:
    """Validation rules run synchronously, in-process, before the write
    commits (ValidationRuleService) — the only place that resolves their
    `lookup` condition nodes and knows what `block_save` means. The pure
    async interpreter this batch runs through has neither, so a validation
    rule reaching it always errors (reproduced end to end against a real
    worker while building ТЗ item 13's balance rule — this was previously
    masked because create_rule never persisted the requested rule_type at
    all, see test_rules.py::test_create_rule_persists_the_requested_rule_type,
    so no validation rule had ever actually reached this code path with its
    real rule_type intact until that was fixed). A mix of rule types on the
    same entity+event must dispatch only the non-validation ones."""
    from app.models.logic import Rule

    app_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    record_id = uuid.uuid4()

    validation_rule = Rule(
        app_id=app_id, entity_id=entity_id, name="Block if too big", rule_type="validation",
        trigger={"event": "record.created", "watch_fields": []},
        conditions={"type": "compare", "field": "amount", "op": "gt",
                    "value": {"type": "lookup", "entity_id": str(uuid.uuid4()), "field": "x", "agg": "sum", "filter": {}}},
        actions=[{"type": "block_save", "message": "too big"}],
        priority=10, is_active=True,
    )
    automation_rule = Rule(
        app_id=app_id, entity_id=entity_id, name="Flag it", rule_type="automation",
        trigger={"event": "record.created", "watch_fields": []},
        conditions={}, actions=[{"type": "set_field", "field": "flagged", "value": {"type": "literal", "value": True}}],
        priority=50, is_active=True,
    )
    db_session.add(validation_rule)
    db_session.add(automation_rule)
    await db_session.flush()

    mock_task = MagicMock()
    mock_task.id = "mock-task-id"

    with patch(
        "app.worker.tasks.sandbox.execute_rules_batch.apply_async",
        return_value=mock_task,
    ) as mock_apply:
        svc = RuleService(db_session)
        task_id = await svc.evaluate_rules_for_event(
            app_id, entity_id, record_id, {"amount": 1}, "record.created"
        )
        assert task_id == "mock-task-id"
        dispatched_ids = {r["id"] for r in mock_apply.call_args.kwargs["kwargs"]["rules"]}
        assert dispatched_ids == {str(automation_rule.id)}


@pytest.mark.asyncio
async def test_only_validation_rules_means_nothing_is_dispatched(db_session: AsyncSession) -> None:
    from app.models.logic import Rule

    app_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    record_id = uuid.uuid4()

    db_session.add(Rule(
        app_id=app_id, entity_id=entity_id, name="Only validation", rule_type="validation",
        trigger={"event": "record.created", "watch_fields": []},
        conditions={}, actions=[{"type": "block_save"}], priority=10, is_active=True,
    ))
    await db_session.flush()

    with patch(
        "app.worker.tasks.sandbox.execute_rules_batch.apply_async",
    ) as mock_apply:
        svc = RuleService(db_session)
        task_id = await svc.evaluate_rules_for_event(
            app_id, entity_id, record_id, {}, "record.created"
        )
        assert task_id is None
        mock_apply.assert_not_called()


@pytest.mark.asyncio
async def test_evaluate_rules_sorts_by_priority(db_session: AsyncSession) -> None:
    """Multiple active rules are dispatched as ONE batch task, sorted ascending
    by priority — not as one task per rule (that couldn't guarantee order)."""
    from app.models.logic import Rule

    app_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    record_id = uuid.uuid4()

    for priority, name in [(50, "low"), (1, "high"), (10, "mid")]:
        db_session.add(Rule(
            app_id=app_id, entity_id=entity_id, name=name,
            trigger={"event": "record.created", "watch_fields": []},
            conditions={}, actions=[], priority=priority, is_active=True,
        ))
    await db_session.flush()

    mock_task = MagicMock()
    mock_task.id = "mock-task-id"

    with patch(
        "app.worker.tasks.sandbox.execute_rules_batch.apply_async",
        return_value=mock_task,
    ) as mock_apply:
        svc = RuleService(db_session)
        task_id = await svc.evaluate_rules_for_event(
            app_id, entity_id, record_id, {}, "record.created"
        )
        assert task_id == "mock-task-id"
        assert mock_apply.call_count == 1  # one batch, not one task per rule
        rules_kwarg = mock_apply.call_args.kwargs["kwargs"]["rules"]
        assert [r["priority"] for r in rules_kwarg] == [1, 10, 50]


# ------------------------------------------------------------------
# Integration: POST /records calls evaluate_rules_for_event
# ------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_record_triggers_rule_evaluation(
    client: AsyncClient, builder: User
) -> None:
    """POST /records should call evaluate_rules_for_event (mocked — no Celery needed)."""
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    field_resp = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/fields",
        json={"name": "note", "display_name": "Note", "field_type": "text"},
        headers=headers,
    )
    assert field_resp.status_code == 201, field_resp.text

    # Create and activate a rule
    rule_resp = await client.post(
        f"/api/v1/apps/{app_id}/rules",
        json=_rule_payload(entity_id, "record.created"),
        headers=headers,
    )
    assert rule_resp.status_code == 201
    rule_id = rule_resp.json()["id"]
    await client.post(f"/api/v1/apps/{app_id}/rules/{rule_id}/activate", headers=headers)

    mock_task = MagicMock()
    mock_task.id = "mock-task-123"

    with patch(
        "app.worker.tasks.sandbox.execute_rules_batch.apply_async",
        return_value=mock_task,
    ) as mock_apply:
        resp = await client.post(
            f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
            json={"payload": {"note": "hello"}},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        # evaluate_rules_for_event was called → apply_async was invoked
        assert mock_apply.call_count == 1
        called_context = mock_apply.call_args.kwargs["kwargs"]["context"]
        assert called_context["event"] == "record.created"
        assert called_context["record_id"]  # not empty


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_record_triggers_rule_evaluation(
    client: AsyncClient, builder: User
) -> None:
    """PATCH /records should call evaluate_rules_for_event with changed_fields."""
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    field_resp = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/fields",
        json={"name": "note", "display_name": "Note", "field_type": "text"},
        headers=headers,
    )
    assert field_resp.status_code == 201, field_resp.text

    rule_resp = await client.post(
        f"/api/v1/apps/{app_id}/rules",
        json=_rule_payload(entity_id, "record.updated"),
        headers=headers,
    )
    rule_id = rule_resp.json()["id"]
    await client.post(f"/api/v1/apps/{app_id}/rules/{rule_id}/activate", headers=headers)

    # Create a record first
    rec_resp = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {"note": "original"}},
        headers=headers,
    )
    record_id = rec_resp.json()["id"]

    mock_task = MagicMock()
    mock_task.id = "mock-task-456"

    with patch(
        "app.worker.tasks.sandbox.execute_rules_batch.apply_async",
        return_value=mock_task,
    ) as mock_apply:
        patch_resp = await client.patch(
            f"/api/v1/apps/{app_id}/entities/{entity_id}/records/{record_id}",
            json={"payload": {"note": "updated"}},
            headers=headers,
        )
        assert patch_resp.status_code == 200, patch_resp.text
        assert mock_apply.call_count == 1
        ctx = mock_apply.call_args.kwargs["kwargs"]["context"]
        assert ctx["event"] == "record.updated"
        assert "note" in ctx["changed_fields"]
        assert ctx["record_id"] == record_id
