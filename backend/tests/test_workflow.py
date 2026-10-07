"""
Workflow Engine tests.

Unit tests: FSM evaluator (guards, roles, terminal state, enter/exit actions).
Integration tests: definition CRUD, instance lifecycle, transition, concurrent modification.
"""

import uuid

import pytest
from app.core.security import hash_password
from app.engine.fsm import (
    FSMSpec,
    FSMTransitionResult,
    GuardNotMetError,
    InsufficientRolesError,
    StateSpec,
    TerminalStateError,
    TransitionNotFoundError,
    TransitionSpec,
    enter_initial_state,
    execute_fsm_transition,
)
from app.models.identity import Role, User, UserRole
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ==================================================================
# Helpers
# ==================================================================


def _state(
    name: str,
    is_terminal: bool = False,
    sla_seconds: int | None = None,
    on_enter: list[dict] | None = None,
    on_exit: list[dict] | None = None,
    sla_breach: list[dict] | None = None,
    escalation_levels: list[dict] | None = None,
) -> StateSpec:
    return StateSpec(
        name=name,
        display_name=name.title(),
        is_terminal=is_terminal,
        sla_seconds=sla_seconds,
        on_enter_actions=on_enter or [],
        on_exit_actions=on_exit or [],
        sla_breach_actions=sla_breach or [],
        escalation_levels=escalation_levels or [],
    )


def _transition(
    name: str,
    from_state: str,
    to_state: str,
    guard: dict | None = None,
    actions: list[dict] | None = None,
    required_roles: list[str] | None = None,
) -> TransitionSpec:
    return TransitionSpec(
        id=str(uuid.uuid4()),
        name=name,
        display_name=name.replace("_", " ").title(),
        from_state=from_state,
        to_state=to_state,
        guard_conditions=guard or {},
        actions=actions or [],
        required_roles=required_roles or [],
    )


def _simple_spec() -> FSMSpec:
    """draft → submit → review → approve → done (terminal)"""
    return FSMSpec(
        workflow_id=str(uuid.uuid4()),
        initial_state="draft",
        states={
            "draft": _state("draft"),
            "review": _state("review", sla_seconds=3600),
            "done": _state("done", is_terminal=True),
        },
        transitions=[
            _transition("submit", "draft", "review"),
            _transition("approve", "review", "done"),
        ],
    )


def _ctx_ids() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.uuid4(), uuid.uuid4()


# ==================================================================
# Unit: FSM spec helpers
# ==================================================================


class TestFSMSpec:
    def test_get_transitions_from(self) -> None:
        spec = _simple_spec()
        trs = spec.get_transitions_from("draft")
        assert len(trs) == 1
        assert trs[0].name == "submit"

    def test_get_transitions_from_terminal(self) -> None:
        spec = _simple_spec()
        assert spec.get_transitions_from("done") == []

    def test_find_transition_exists(self) -> None:
        spec = _simple_spec()
        tr = spec.find_transition("review", "approve")
        assert tr is not None
        assert tr.to_state == "done"

    def test_find_transition_missing(self) -> None:
        spec = _simple_spec()
        assert spec.find_transition("draft", "approve") is None

    def test_get_state(self) -> None:
        spec = _simple_spec()
        assert spec.get_state("draft") is not None
        assert spec.get_state("nonexistent") is None


# ==================================================================
# Unit: execute_fsm_transition — happy paths
# ==================================================================


class TestFSMTransitionHappy:
    def test_basic_transition(self) -> None:
        spec = _simple_spec()
        entity_id, app_id = _ctx_ids()
        result = execute_fsm_transition(spec, "draft", "submit", {}, entity_id, app_id)
        assert isinstance(result, FSMTransitionResult)
        assert result.new_state == "review"
        assert result.errors == []

    def test_sla_seconds_propagated(self) -> None:
        spec = _simple_spec()
        entity_id, app_id = _ctx_ids()
        result = execute_fsm_transition(spec, "draft", "submit", {}, entity_id, app_id)
        assert result.sla_seconds == 3600

    def test_no_sla_when_new_state_has_none(self) -> None:
        spec = _simple_spec()
        entity_id, app_id = _ctx_ids()
        result = execute_fsm_transition(spec, "review", "approve", {}, entity_id, app_id)
        assert result.sla_seconds is None

    def test_transition_with_guard_met(self) -> None:
        spec = FSMSpec(
            workflow_id=str(uuid.uuid4()),
            initial_state="new",
            states={"new": _state("new"), "approved": _state("approved")},
            transitions=[
                _transition(
                    "approve",
                    "new",
                    "approved",
                    guard={"type": "compare", "field": "amount", "op": "gt", "value": 0},
                ),
            ],
        )
        entity_id, app_id = _ctx_ids()
        result = execute_fsm_transition(spec, "new", "approve", {"amount": 100}, entity_id, app_id)
        assert result.new_state == "approved"

    def test_transition_actions_field_mutation(self) -> None:
        spec = FSMSpec(
            workflow_id=str(uuid.uuid4()),
            initial_state="draft",
            states={"draft": _state("draft"), "submitted": _state("submitted")},
            transitions=[
                _transition(
                    "submit",
                    "draft",
                    "submitted",
                    actions=[
                        {
                            "type": "set_field",
                            "field": "submitted_flag",
                            "value": {"type": "literal", "value": True},
                        },
                    ],
                ),
            ],
        )
        entity_id, app_id = _ctx_ids()
        result = execute_fsm_transition(spec, "draft", "submit", {}, entity_id, app_id)
        assert result.field_mutations.get("submitted_flag") is True

    def test_on_exit_actions_run_before_transition_actions(self) -> None:
        spec = FSMSpec(
            workflow_id=str(uuid.uuid4()),
            initial_state="a",
            states={
                "a": _state(
                    "a",
                    on_exit=[
                        {
                            "type": "set_field",
                            "field": "step",
                            "value": {"type": "literal", "value": "exit_a"},
                        },
                    ],
                ),
                "b": _state(
                    "b",
                    on_enter=[
                        {
                            "type": "set_field",
                            "field": "step",
                            "value": {"type": "literal", "value": "enter_b"},
                        },
                    ],
                ),
            },
            transitions=[
                _transition(
                    "go",
                    "a",
                    "b",
                    actions=[
                        {
                            "type": "set_field",
                            "field": "tr_step",
                            "value": {"type": "literal", "value": "transition"},
                        },
                    ],
                ),
            ],
        )
        entity_id, app_id = _ctx_ids()
        result = execute_fsm_transition(spec, "a", "go", {}, entity_id, app_id)
        # on_enter_actions for "b" wins (runs last) and overwrites "step"
        assert result.field_mutations.get("step") == "enter_b"
        assert result.field_mutations.get("tr_step") == "transition"

    def test_notification_from_on_enter(self) -> None:
        spec = FSMSpec(
            workflow_id=str(uuid.uuid4()),
            initial_state="draft",
            states={
                "draft": _state("draft"),
                "review": _state(
                    "review",
                    on_enter=[
                        {
                            "type": "send_notification",
                            "to": "reviewer@example.com",
                            "subject": "New review request",
                            "template": "",
                        },
                    ],
                ),
            },
            transitions=[_transition("submit", "draft", "review")],
        )
        entity_id, app_id = _ctx_ids()
        result = execute_fsm_transition(spec, "draft", "submit", {}, entity_id, app_id)
        assert len(result.notifications) == 1
        assert result.notifications[0]["to"] == "reviewer@example.com"


# ==================================================================
# Unit: execute_fsm_transition — error paths
# ==================================================================


class TestFSMTransitionErrors:
    def test_transition_not_found(self) -> None:
        spec = _simple_spec()
        entity_id, app_id = _ctx_ids()
        with pytest.raises(TransitionNotFoundError):
            execute_fsm_transition(spec, "draft", "nonexistent", {}, entity_id, app_id)

    def test_terminal_state_raises(self) -> None:
        spec = _simple_spec()
        entity_id, app_id = _ctx_ids()
        with pytest.raises(TerminalStateError):
            execute_fsm_transition(spec, "done", "anything", {}, entity_id, app_id)

    def test_guard_not_met(self) -> None:
        spec = FSMSpec(
            workflow_id=str(uuid.uuid4()),
            initial_state="new",
            states={"new": _state("new"), "approved": _state("approved")},
            transitions=[
                _transition(
                    "approve",
                    "new",
                    "approved",
                    guard={"type": "compare", "field": "amount", "op": "gt", "value": 100},
                ),
            ],
        )
        entity_id, app_id = _ctx_ids()
        with pytest.raises(GuardNotMetError):
            execute_fsm_transition(spec, "new", "approve", {"amount": 50}, entity_id, app_id)

    def test_insufficient_roles(self) -> None:
        spec = FSMSpec(
            workflow_id=str(uuid.uuid4()),
            initial_state="draft",
            states={"draft": _state("draft"), "published": _state("published")},
            transitions=[
                _transition("publish", "draft", "published", required_roles=["admin"]),
            ],
        )
        entity_id, app_id = _ctx_ids()
        with pytest.raises(InsufficientRolesError) as exc_info:
            execute_fsm_transition(
                spec, "draft", "publish", {}, entity_id, app_id, actor_roles=["viewer"]
            )
        assert "admin" in exc_info.value.required_roles

    def test_sufficient_role_passes(self) -> None:
        spec = FSMSpec(
            workflow_id=str(uuid.uuid4()),
            initial_state="draft",
            states={"draft": _state("draft"), "published": _state("published")},
            transitions=[
                _transition("publish", "draft", "published", required_roles=["admin", "editor"]),
            ],
        )
        entity_id, app_id = _ctx_ids()
        result = execute_fsm_transition(
            spec, "draft", "publish", {}, entity_id, app_id, actor_roles=["editor"]
        )
        assert result.new_state == "published"


# ==================================================================
# Unit: enter_initial_state
# ==================================================================


class TestEnterInitialState:
    def test_runs_on_enter_actions(self) -> None:
        spec = FSMSpec(
            workflow_id=str(uuid.uuid4()),
            initial_state="new",
            states={
                "new": _state(
                    "new",
                    on_enter=[
                        {
                            "type": "set_field",
                            "field": "initialized",
                            "value": {"type": "literal", "value": True},
                        },
                    ],
                ),
            },
            transitions=[],
        )
        entity_id, app_id = _ctx_ids()
        result = enter_initial_state(spec, {}, entity_id, app_id)
        assert result.new_state == "new"
        assert result.field_mutations.get("initialized") is True

    def test_no_enter_actions_returns_empty(self) -> None:
        spec = _simple_spec()
        entity_id, app_id = _ctx_ids()
        result = enter_initial_state(spec, {}, entity_id, app_id)
        assert result.new_state == "draft"
        assert result.field_mutations == {}

    def test_sla_propagated(self) -> None:
        spec = FSMSpec(
            workflow_id=str(uuid.uuid4()),
            initial_state="active",
            states={"active": _state("active", sla_seconds=7200)},
            transitions=[],
        )
        entity_id, app_id = _ctx_ids()
        result = enter_initial_state(spec, {}, entity_id, app_id)
        assert result.sla_seconds == 7200


# ==================================================================
# Fixtures
# ==================================================================


@pytest.fixture()
async def builder(db_session: AsyncSession) -> User:
    for role_id in ("app_builder",):
        if not await db_session.get(Role, role_id):
            db_session.add(Role(id=role_id, display_name="App Builder", is_system=True))
    user = User(
        email="wf_builder@example.com",
        display_name="WF Builder",
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
    slug = f"wf-app-{uuid.uuid4().hex[:6]}"
    app_resp = await client.post(
        "/api/v1/apps",
        json={"slug": slug, "name": "WF Test App"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert app_resp.status_code == 201, app_resp.text
    app_id = app_resp.json()["id"]

    ent_resp = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "ticket", "display_name": "Ticket"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ent_resp.status_code == 201, ent_resp.text
    entity_id = ent_resp.json()["id"]
    return app_id, entity_id


async def _create_full_workflow(
    client: AsyncClient, token: str, app_id: str, entity_id: str
) -> dict[str, str]:
    """
    Create a complete workflow: draft → submit → review → close (terminal).
    Returns dict with workflow_id and all state/transition IDs.
    """
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/apps/{app_id}/workflows"

    wf = await client.post(
        base,
        json={
            "entity_id": entity_id,
            "name": "Ticket Workflow",
            "initial_state": "draft",
        },
        headers=headers,
    )
    assert wf.status_code == 201, wf.text
    workflow_id = wf.json()["id"]

    ids: dict[str, str] = {"workflow_id": workflow_id}

    for state in [
        {"name": "draft", "display_name": "Draft"},
        {"name": "review", "display_name": "In Review"},
        {"name": "closed", "display_name": "Closed", "is_terminal": True},
    ]:
        r = await client.post(f"{base}/{workflow_id}/states", json=state, headers=headers)
        assert r.status_code == 201, r.text
        ids[f"state_{state['name']}"] = r.json()["id"]

    for tr in [
        {"name": "submit", "display_name": "Submit", "from_state": "draft", "to_state": "review"},
        {"name": "close", "display_name": "Close", "from_state": "review", "to_state": "closed"},
    ]:
        r = await client.post(f"{base}/{workflow_id}/transitions", json=tr, headers=headers)
        assert r.status_code == 201, r.text
        ids[f"tr_{tr['name']}"] = r.json()["id"]

    # Activate workflow
    act = await client.post(f"{base}/{workflow_id}/activate", headers=headers)
    assert act.status_code == 200

    return ids


# ==================================================================
# Integration: WorkflowDef CRUD
# ==================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_workflow(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"/api/v1/apps/{app_id}/workflows",
        json={"entity_id": entity_id, "name": "My Workflow", "initial_state": "draft"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Workflow"
    assert data["is_active"] is False
    assert data["initial_state"] == "draft"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_workflow_not_found(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, _ = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"/api/v1/apps/{app_id}/workflows/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_activate_deactivate_workflow(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/apps/{app_id}/workflows"

    wf = await client.post(
        base,
        json={"entity_id": entity_id, "name": "WF", "initial_state": "new"},
        headers=headers,
    )
    wf_id = wf.json()["id"]

    act = await client.post(f"{base}/{wf_id}/activate", headers=headers)
    assert act.status_code == 200
    assert act.json()["is_active"] is True

    deact = await client.post(f"{base}/{wf_id}/deactivate", headers=headers)
    assert deact.status_code == 200
    assert deact.json()["is_active"] is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_workflow(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/apps/{app_id}/workflows"

    wf = await client.post(
        base,
        json={"entity_id": entity_id, "name": "Temp WF", "initial_state": "new"},
        headers=headers,
    )
    wf_id = wf.json()["id"]

    del_resp = await client.delete(f"{base}/{wf_id}", headers=headers)
    assert del_resp.status_code == 204

    get_resp = await client.get(f"{base}/{wf_id}", headers=headers)
    assert get_resp.status_code == 404


# ==================================================================
# Integration: state + transition CRUD
# ==================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_state(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/apps/{app_id}/workflows"

    wf = await client.post(
        base,
        json={"entity_id": entity_id, "name": "WF", "initial_state": "draft"},
        headers=headers,
    )
    wf_id = wf.json()["id"]

    state_resp = await client.post(
        f"{base}/{wf_id}/states",
        json={"name": "draft", "display_name": "Draft", "sla_seconds": 3600},
        headers=headers,
    )
    assert state_resp.status_code == 201
    assert state_resp.json()["name"] == "draft"
    assert state_resp.json()["sla_seconds"] == 3600


@pytest.mark.integration
@pytest.mark.asyncio
async def test_state_name_must_be_lowercase(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/apps/{app_id}/workflows"

    wf = await client.post(
        base,
        json={"entity_id": entity_id, "name": "WF", "initial_state": "draft"},
        headers=headers,
    )
    wf_id = wf.json()["id"]

    resp = await client.post(
        f"{base}/{wf_id}/states",
        json={"name": "MyState", "display_name": "My State"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_transition(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/apps/{app_id}/workflows"

    wf = await client.post(
        base,
        json={"entity_id": entity_id, "name": "WF", "initial_state": "draft"},
        headers=headers,
    )
    wf_id = wf.json()["id"]

    tr_resp = await client.post(
        f"{base}/{wf_id}/transitions",
        json={
            "name": "submit",
            "display_name": "Submit",
            "from_state": "draft",
            "to_state": "review",
        },
        headers=headers,
    )
    assert tr_resp.status_code == 201
    assert tr_resp.json()["from_state"] == "draft"
    assert tr_resp.json()["to_state"] == "review"


# ==================================================================
# Integration: instance lifecycle
# ==================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_instance(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    ids = await _create_full_workflow(client, token, app_id, entity_id)
    headers = {"Authorization": f"Bearer {token}"}
    wf_id = ids["workflow_id"]
    record_id = str(uuid.uuid4())

    resp = await client.post(
        f"/api/v1/apps/{app_id}/workflows/{wf_id}/instances",
        json={"record_id": record_id, "record_payload": {"title": "Bug #1"}},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["current_state"] == "draft"
    assert data["record_id"] == record_id
    assert data["version"] == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_instance_duplicate_returns_409(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    ids = await _create_full_workflow(client, token, app_id, entity_id)
    headers = {"Authorization": f"Bearer {token}"}
    wf_id = ids["workflow_id"]
    record_id = str(uuid.uuid4())
    body = {"record_id": record_id, "record_payload": {}}

    r1 = await client.post(
        f"/api/v1/apps/{app_id}/workflows/{wf_id}/instances", json=body, headers=headers
    )
    assert r1.status_code == 201

    r2 = await client.post(
        f"/api/v1/apps/{app_id}/workflows/{wf_id}/instances", json=body, headers=headers
    )
    assert r2.status_code == 409


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execute_transition_success(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    ids = await _create_full_workflow(client, token, app_id, entity_id)
    headers = {"Authorization": f"Bearer {token}"}
    wf_id = ids["workflow_id"]
    record_id = str(uuid.uuid4())

    start = await client.post(
        f"/api/v1/apps/{app_id}/workflows/{wf_id}/instances",
        json={"record_id": record_id, "record_payload": {}},
        headers=headers,
    )
    instance_id = start.json()["id"]

    tr_resp = await client.post(
        f"/api/v1/apps/{app_id}/workflows/{wf_id}/instances/{instance_id}/transition",
        json={"transition_name": "submit", "record_payload": {}},
        headers=headers,
    )
    assert tr_resp.status_code == 200
    data = tr_resp.json()
    assert data["instance"]["current_state"] == "review"
    assert data["instance"]["version"] == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execute_transition_full_cycle(client: AsyncClient, builder: User) -> None:
    """draft → review → closed (terminal)"""
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    ids = await _create_full_workflow(client, token, app_id, entity_id)
    headers = {"Authorization": f"Bearer {token}"}
    wf_id = ids["workflow_id"]
    record_id = str(uuid.uuid4())

    start = await client.post(
        f"/api/v1/apps/{app_id}/workflows/{wf_id}/instances",
        json={"record_id": record_id, "record_payload": {}},
        headers=headers,
    )
    instance_id = start.json()["id"]
    base = f"/api/v1/apps/{app_id}/workflows/{wf_id}/instances/{instance_id}"

    await client.post(
        f"{base}/transition",
        json={"transition_name": "submit", "record_payload": {}},
        headers=headers,
    )

    close_resp = await client.post(
        f"{base}/transition",
        json={"transition_name": "close", "record_payload": {}},
        headers=headers,
    )
    assert close_resp.status_code == 200
    assert close_resp.json()["instance"]["current_state"] == "closed"
    assert close_resp.json()["instance"]["completed_at"] is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execute_transition_invalid_name(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    ids = await _create_full_workflow(client, token, app_id, entity_id)
    headers = {"Authorization": f"Bearer {token}"}
    wf_id = ids["workflow_id"]
    record_id = str(uuid.uuid4())

    start = await client.post(
        f"/api/v1/apps/{app_id}/workflows/{wf_id}/instances",
        json={"record_id": record_id, "record_payload": {}},
        headers=headers,
    )
    instance_id = start.json()["id"]

    resp = await client.post(
        f"/api/v1/apps/{app_id}/workflows/{wf_id}/instances/{instance_id}/transition",
        json={"transition_name": "nonexistent", "record_payload": {}},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_transition_log_records_history(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    ids = await _create_full_workflow(client, token, app_id, entity_id)
    headers = {"Authorization": f"Bearer {token}"}
    wf_id = ids["workflow_id"]
    record_id = str(uuid.uuid4())

    start = await client.post(
        f"/api/v1/apps/{app_id}/workflows/{wf_id}/instances",
        json={"record_id": record_id, "record_payload": {}},
        headers=headers,
    )
    instance_id = start.json()["id"]
    base = f"/api/v1/apps/{app_id}/workflows/{wf_id}/instances/{instance_id}"

    await client.post(
        f"{base}/transition",
        json={"transition_name": "submit", "record_payload": {}},
        headers=headers,
    )

    log_resp = await client.get(f"{base}/log", headers=headers)
    assert log_resp.status_code == 200
    log = log_resp.json()
    assert len(log) == 2  # start entry + submit transition
    assert log[0]["from_state"] is None  # instance start
    assert log[0]["to_state"] == "draft"
    assert log[1]["from_state"] == "draft"
    assert log[1]["to_state"] == "review"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_available_transitions(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    ids = await _create_full_workflow(client, token, app_id, entity_id)
    headers = {"Authorization": f"Bearer {token}"}
    wf_id = ids["workflow_id"]
    record_id = str(uuid.uuid4())

    start = await client.post(
        f"/api/v1/apps/{app_id}/workflows/{wf_id}/instances",
        json={"record_id": record_id, "record_payload": {}},
        headers=headers,
    )
    instance_id = start.json()["id"]

    resp = await client.get(
        f"/api/v1/apps/{app_id}/workflows/{wf_id}/instances/{instance_id}/transitions",
        headers=headers,
    )
    assert resp.status_code == 200
    names = [t["name"] for t in resp.json()]
    assert "submit" in names
    assert "close" not in names  # not available from "draft"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_inactive_workflow_fails(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/apps/{app_id}/workflows"

    wf = await client.post(
        base,
        json={"entity_id": entity_id, "name": "Inactive WF", "initial_state": "new"},
        headers=headers,
    )
    wf_id = wf.json()["id"]

    resp = await client.post(
        f"{base}/{wf_id}/instances",
        json={"record_id": str(uuid.uuid4()), "record_payload": {}},
        headers=headers,
    )
    assert resp.status_code == 422
