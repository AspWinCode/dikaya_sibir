"""Pre-publish integrity check tests (ТЗ 3.11.1).

Covers all four check categories directly through the same CRUD endpoints a
real user would use — none of the underlying create/delete endpoints
(fields, states, transitions) validate these cross-references themselves,
so the check is the only thing standing between a broken app and publish.
"""

from __future__ import annotations

import uuid

import pytest
from app.core.security import hash_password
from app.models.identity import Role, User, UserRole
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


@pytest.fixture()
async def builder(db_session: AsyncSession) -> User:
    for role_id in ("app_builder",):
        if not await db_session.get(Role, role_id):
            db_session.add(Role(id=role_id, display_name="App Builder", is_system=True))
    user = User(
        email="publish_builder@example.com",
        display_name="Publish Builder",
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


async def _create_app(client: AsyncClient, token: str) -> str:
    slug = f"pub-app-{uuid.uuid4().hex[:6]}"
    r = await client.post(
        "/api/v1/apps",
        json={"slug": slug, "name": "Publish Test App"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _create_entity(client: AsyncClient, token: str, app_id: str, slug: str) -> str:
    r = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": slug, "display_name": slug.title()},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _create_field(
    client: AsyncClient, token: str, app_id: str, entity_id: str, name: str
) -> str:
    r = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/fields",
        json={"name": name, "display_name": name, "field_type": "text"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------
# Baseline
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_app_has_no_issues(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _create_app(client, token)

    resp = await client.get(f"/api/v1/apps/{app_id}/publish/check", headers=_headers(token))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["can_publish"] is True
    assert data["issues"] == []


@pytest.mark.asyncio
async def test_check_does_not_publish(client: AsyncClient, builder: User) -> None:
    """GET /publish/check is a dry run — it must not flip is_published."""
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _create_app(client, token)

    await client.get(f"/api/v1/apps/{app_id}/publish/check", headers=_headers(token))

    app_resp = await client.get(f"/api/v1/apps/{app_id}", headers=_headers(token))
    assert app_resp.json()["is_published"] is False


# ------------------------------------------------------------------
# Blocks / pages without a data source
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_page_missing_entity_id_is_a_warning(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _create_app(client, token)

    await client.post(
        f"/api/v1/apps/{app_id}/pages",
        json={"slug": "orphan", "title": "Orphan Page", "layout": {"view_type": "table"}},
        headers=_headers(token),
    )

    resp = await client.get(f"/api/v1/apps/{app_id}/publish/check", headers=_headers(token))
    data = resp.json()
    assert data["can_publish"] is True  # warning only
    assert any(
        i["category"] == "block_no_source" and i["severity"] == "warning" for i in data["issues"]
    )


@pytest.mark.asyncio
async def test_page_with_dangling_entity_id_is_an_error(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _create_app(client, token)

    await client.post(
        f"/api/v1/apps/{app_id}/pages",
        json={
            "slug": "dangling",
            "title": "Dangling Page",
            "layout": {"view_type": "table", "entity_id": str(uuid.uuid4())},
        },
        headers=_headers(token),
    )

    resp = await client.get(f"/api/v1/apps/{app_id}/publish/check", headers=_headers(token))
    data = resp.json()
    assert data["can_publish"] is False
    assert any(
        i["category"] == "block_no_source" and i["severity"] == "error" for i in data["issues"]
    )


@pytest.mark.asyncio
async def test_block_with_valid_entity_id_is_not_flagged(
    client: AsyncClient, builder: User
) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _create_app(client, token)
    entity_id = await _create_entity(client, token, app_id, "widgets")

    await client.post(
        f"/api/v1/apps/{app_id}/pages",
        json={
            "slug": "ok-page",
            "title": "OK Page",
            "layout": {},
            "blocks": [{"id": "b1", "type": "record_card", "config": {"entity_id": entity_id}}],
        },
        headers=_headers(token),
    )

    resp = await client.get(f"/api/v1/apps/{app_id}/publish/check", headers=_headers(token))
    data = resp.json()
    assert data["can_publish"] is True
    assert data["issues"] == []


@pytest.mark.asyncio
async def test_block_with_dangling_entity_id_is_an_error(
    client: AsyncClient, builder: User
) -> None:
    """A block's entity_id is checked against the app's live entities when
    the page is saved (ТЗ item 4) — so a block can no longer be created
    pointing at an entity_id that never existed. This test instead covers
    the reference going stale AFTER the fact: the entity existed when the
    block was saved, then got deleted — exactly the case the pre-publish
    check exists to catch, since nothing re-validates saved pages when an
    entity disappears."""
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _create_app(client, token)
    entity_id = await _create_entity(client, token, app_id, "soon_to_be_deleted")

    await client.post(
        f"/api/v1/apps/{app_id}/pages",
        json={
            "slug": "broken-block",
            "title": "Broken Block",
            "layout": {},
            "blocks": [{"id": "b1", "type": "pivot", "config": {"entity_id": entity_id}}],
        },
        headers=_headers(token),
    )
    del_resp = await client.delete(
        f"/api/v1/apps/{app_id}/entities/{entity_id}", headers=_headers(token)
    )
    assert del_resp.status_code == 204, del_resp.text

    resp = await client.get(f"/api/v1/apps/{app_id}/publish/check", headers=_headers(token))
    data = resp.json()
    assert data["can_publish"] is False
    assert any(
        i["category"] == "block_no_source" and i["location"].get("block_id") == "b1"
        for i in data["issues"]
    )


# ------------------------------------------------------------------
# Rules with no actions
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_rule_without_actions_is_a_warning(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _create_app(client, token)
    entity_id = await _create_entity(client, token, app_id, "orders")

    rule_resp = await client.post(
        f"/api/v1/apps/{app_id}/rules",
        json={
            "entity_id": entity_id,
            "name": "Empty rule",
            "trigger": {"event": "record.created", "watch_fields": []},
            "conditions": {},
            "actions": [],
            "priority": 10,
        },
        headers=_headers(token),
    )
    assert rule_resp.status_code == 201, rule_resp.text
    rule_id = rule_resp.json()["id"]
    await client.post(f"/api/v1/apps/{app_id}/rules/{rule_id}/activate", headers=_headers(token))

    resp = await client.get(f"/api/v1/apps/{app_id}/publish/check", headers=_headers(token))
    data = resp.json()
    assert data["can_publish"] is True
    assert any(i["category"] == "rule_empty" for i in data["issues"])


@pytest.mark.asyncio
async def test_inactive_rule_without_actions_is_not_flagged(
    client: AsyncClient, builder: User
) -> None:
    """A rule left inactive/in-draft shouldn't block or clutter the check."""
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _create_app(client, token)
    entity_id = await _create_entity(client, token, app_id, "orders")

    await client.post(
        f"/api/v1/apps/{app_id}/rules",
        json={
            "entity_id": entity_id,
            "name": "Draft rule",
            "trigger": {"event": "record.created", "watch_fields": []},
            "conditions": {},
            "actions": [],
            "priority": 10,
        },
        headers=_headers(token),
    )

    resp = await client.get(f"/api/v1/apps/{app_id}/publish/check", headers=_headers(token))
    assert resp.json()["issues"] == []


# ------------------------------------------------------------------
# Workflow: hanging transitions / unreachable initial state
# ------------------------------------------------------------------


async def _create_workflow(client: AsyncClient, token: str, app_id: str, entity_id: str) -> str:
    r = await client.post(
        f"/api/v1/apps/{app_id}/workflows",
        json={"entity_id": entity_id, "name": "Approval", "initial_state": "draft"},
        headers=_headers(token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _create_state(
    client: AsyncClient,
    token: str,
    app_id: str,
    workflow_id: str,
    name: str,
    terminal: bool = False,
) -> str:
    r = await client.post(
        f"/api/v1/apps/{app_id}/workflows/{workflow_id}/states",
        json={"name": name, "display_name": name.title(), "is_terminal": terminal},
        headers=_headers(token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_workflow_initial_state_missing_is_an_error(
    client: AsyncClient, builder: User
) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _create_app(client, token)
    entity_id = await _create_entity(client, token, app_id, "invoices")
    workflow_id = await _create_workflow(client, token, app_id, entity_id)
    # No states created at all — initial_state "draft" doesn't exist.
    await client.post(
        f"/api/v1/apps/{app_id}/workflows/{workflow_id}/activate", headers=_headers(token)
    )

    resp = await client.get(f"/api/v1/apps/{app_id}/publish/check", headers=_headers(token))
    data = resp.json()
    assert data["can_publish"] is False
    assert any(
        i["category"] == "workflow_transition" and "начальный этап" in i["message"]
        for i in data["issues"]
    )


@pytest.mark.asyncio
async def test_workflow_transition_to_nonexistent_state_is_an_error(
    client: AsyncClient, builder: User
) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _create_app(client, token)
    entity_id = await _create_entity(client, token, app_id, "invoices")
    workflow_id = await _create_workflow(client, token, app_id, entity_id)
    await _create_state(client, token, app_id, workflow_id, "draft")
    # No "approved" state exists — the create_transition endpoint doesn't check this itself.
    tr_resp = await client.post(
        f"/api/v1/apps/{app_id}/workflows/{workflow_id}/transitions",
        json={
            "name": "approve",
            "display_name": "Approve",
            "from_state": "draft",
            "to_state": "approved",
        },
        headers=_headers(token),
    )
    assert tr_resp.status_code == 201, tr_resp.text
    await client.post(
        f"/api/v1/apps/{app_id}/workflows/{workflow_id}/activate", headers=_headers(token)
    )

    resp = await client.get(f"/api/v1/apps/{app_id}/publish/check", headers=_headers(token))
    data = resp.json()
    assert data["can_publish"] is False
    assert any(
        i["category"] == "workflow_transition" and "approved" in i["message"]
        for i in data["issues"]
    )


@pytest.mark.asyncio
async def test_workflow_dead_end_state_is_a_warning(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _create_app(client, token)
    entity_id = await _create_entity(client, token, app_id, "invoices")
    workflow_id = await _create_workflow(client, token, app_id, entity_id)
    await _create_state(client, token, app_id, workflow_id, "draft")
    await _create_state(
        client, token, app_id, workflow_id, "stuck"
    )  # non-terminal, no outgoing transition
    await client.post(
        f"/api/v1/apps/{app_id}/workflows/{workflow_id}/transitions",
        json={
            "name": "advance",
            "display_name": "Advance",
            "from_state": "draft",
            "to_state": "stuck",
        },
        headers=_headers(token),
    )
    await client.post(
        f"/api/v1/apps/{app_id}/workflows/{workflow_id}/activate", headers=_headers(token)
    )

    resp = await client.get(f"/api/v1/apps/{app_id}/publish/check", headers=_headers(token))
    data = resp.json()
    assert data["can_publish"] is True  # dead end is a warning, not an error
    assert any(
        i["category"] == "workflow_transition" and i["severity"] == "warning"
        for i in data["issues"]
    )


@pytest.mark.asyncio
async def test_well_formed_workflow_is_not_flagged(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _create_app(client, token)
    entity_id = await _create_entity(client, token, app_id, "invoices")
    workflow_id = await _create_workflow(client, token, app_id, entity_id)
    await _create_state(client, token, app_id, workflow_id, "draft")
    await _create_state(client, token, app_id, workflow_id, "approved", terminal=True)
    await client.post(
        f"/api/v1/apps/{app_id}/workflows/{workflow_id}/transitions",
        json={
            "name": "approve",
            "display_name": "Approve",
            "from_state": "draft",
            "to_state": "approved",
        },
        headers=_headers(token),
    )
    await client.post(
        f"/api/v1/apps/{app_id}/workflows/{workflow_id}/activate", headers=_headers(token)
    )

    resp = await client.get(f"/api/v1/apps/{app_id}/publish/check", headers=_headers(token))
    assert resp.json()["issues"] == []


# ------------------------------------------------------------------
# Relations pointing at deleted fields
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_relation_field_deleted_after_creation_is_an_error(
    client: AsyncClient, builder: User
) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _create_app(client, token)
    parent_id = await _create_entity(client, token, app_id, "parent")
    child_id = await _create_entity(client, token, app_id, "child")
    field_id = await _create_field(client, token, app_id, child_id, "parent_ref")

    rel_resp = await client.post(
        f"/api/v1/apps/{app_id}/relations",
        json={
            "from_entity_id": child_id,
            "to_entity_id": parent_id,
            "relation_type": "one_to_many",
            "from_field_name": "parent_ref",
        },
        headers=_headers(token),
    )
    assert rel_resp.status_code == 201, rel_resp.text

    # Nothing stops deleting a field a relation still points at.
    del_resp = await client.delete(
        f"/api/v1/apps/{app_id}/entities/{child_id}/fields/{field_id}",
        headers=_headers(token),
    )
    assert del_resp.status_code == 204, del_resp.text

    resp = await client.get(f"/api/v1/apps/{app_id}/publish/check", headers=_headers(token))
    data = resp.json()
    assert data["can_publish"] is False
    assert any(i["category"] == "relation_invalid" for i in data["issues"])


@pytest.mark.asyncio
async def test_relation_with_existing_field_is_not_flagged(
    client: AsyncClient, builder: User
) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _create_app(client, token)
    parent_id = await _create_entity(client, token, app_id, "parent2")
    child_id = await _create_entity(client, token, app_id, "child2")
    await _create_field(client, token, app_id, child_id, "parent_ref")

    await client.post(
        f"/api/v1/apps/{app_id}/relations",
        json={
            "from_entity_id": child_id,
            "to_entity_id": parent_id,
            "relation_type": "one_to_many",
            "from_field_name": "parent_ref",
        },
        headers=_headers(token),
    )

    resp = await client.get(f"/api/v1/apps/{app_id}/publish/check", headers=_headers(token))
    assert resp.json()["issues"] == []


# ------------------------------------------------------------------
# POST /publish actually enforces the block
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_blocked_returns_422_with_issues(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _create_app(client, token)
    await client.post(
        f"/api/v1/apps/{app_id}/pages",
        json={
            "slug": "broken",
            "title": "Broken",
            "layout": {"view_type": "table", "entity_id": str(uuid.uuid4())},
        },
        headers=_headers(token),
    )

    resp = await client.post(f"/api/v1/apps/{app_id}/publish", headers=_headers(token))
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert len(detail["issues"]) >= 1

    app_resp = await client.get(f"/api/v1/apps/{app_id}", headers=_headers(token))
    assert app_resp.json()["is_published"] is False


@pytest.mark.asyncio
async def test_publish_succeeds_with_only_warnings(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _create_app(client, token)
    # Missing entity_id (not dangling) is warning-only — must not block.
    await client.post(
        f"/api/v1/apps/{app_id}/pages",
        json={"slug": "warn-only", "title": "Warn Only", "layout": {"view_type": "table"}},
        headers=_headers(token),
    )

    resp = await client.post(f"/api/v1/apps/{app_id}/publish", headers=_headers(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_published"] is True


@pytest.mark.asyncio
async def test_publish_succeeds_for_clean_app(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _create_app(client, token)

    resp = await client.post(f"/api/v1/apps/{app_id}/publish", headers=_headers(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_published"] is True
