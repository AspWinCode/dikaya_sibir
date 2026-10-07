"""Tests for SequenceService and /sequences endpoint."""

import uuid

import pytest
from app.core.security import hash_password
from app.models.identity import Role, User, UserRole
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ── helpers ──────────────────────────────────────────────────────────────────


def _app_url(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}"


def _seq_url(app_id: str, entity_id: str) -> str:
    return f"/api/v1/apps/{app_id}/entities/{entity_id}/sequences"


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
async def admin_token(client: AsyncClient, db_session: AsyncSession) -> str:
    """Log in as a fresh app_builder user and return an access token."""
    if not await db_session.get(Role, "app_builder"):
        db_session.add(Role(id="app_builder", display_name="App Builder", is_system=True))
    user = User(
        email="seq_builder@example.com",
        display_name="Sequence Builder",
        password_hash=hash_password("Build1234!"),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id="app_builder"))
    await db_session.flush()

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "seq_builder@example.com", "password": "Build1234!"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
async def app_and_entity(client: AsyncClient, admin_token: str):
    """Create a throwaway app + entity and return (app_id, entity_id)."""
    headers = {"Authorization": f"Bearer {admin_token}"}

    slug = f"seq-test-{uuid.uuid4().hex[:8]}"
    app_r = await client.post(
        "/api/v1/apps",
        json={"name": "Seq Test App", "slug": slug, "description": ""},
        headers=headers,
    )
    assert app_r.status_code == 201, app_r.text
    app_id = app_r.json()["id"]

    ent_r = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "orders", "display_name": "Orders"},
        headers=headers,
    )
    assert ent_r.status_code == 201, ent_r.text
    entity_id = ent_r.json()["id"]

    # Add an autonumber field
    field_r = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/fields",
        json={
            "name": "order_no",
            "display_name": "Order #",
            "field_type": "autonumber",
            "is_required": False,
        },
        headers=headers,
    )
    assert field_r.status_code == 201, field_r.text

    return app_id, entity_id, headers


# ── CRUD tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_sequence(client: AsyncClient, app_and_entity):
    app_id, entity_id, headers = app_and_entity
    url = _seq_url(app_id, entity_id)

    r = await client.post(
        url,
        json={"field_name": "order_no", "prefix": "ORD-", "padding": 5, "step": 1},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["prefix"] == "ORD-"
    assert data["padding"] == 5
    assert data["next_value"] == 1


@pytest.mark.asyncio
async def test_list_sequences(client: AsyncClient, app_and_entity):
    app_id, entity_id, headers = app_and_entity
    url = _seq_url(app_id, entity_id)

    await client.post(url, json={"field_name": "order_no", "prefix": "X-"}, headers=headers)
    r = await client.get(url, headers=headers)
    assert r.status_code == 200, r.text
    items = r.json()
    assert isinstance(items, list)
    assert len(items) >= 1


@pytest.mark.asyncio
async def test_update_sequence(client: AsyncClient, app_and_entity):
    app_id, entity_id, headers = app_and_entity
    url = _seq_url(app_id, entity_id)

    create_r = await client.post(
        url, json={"field_name": "order_no", "prefix": "A-"}, headers=headers
    )
    seq_id = create_r.json()["id"]

    patch_r = await client.patch(
        f"{url}/{seq_id}",
        json={"prefix": "B-", "padding": 3},
        headers=headers,
    )
    assert patch_r.status_code == 200, patch_r.text
    assert patch_r.json()["prefix"] == "B-"
    assert patch_r.json()["padding"] == 3


@pytest.mark.asyncio
async def test_next_value_previews_without_consuming(client: AsyncClient, app_and_entity):
    """POST .../next is a preview for UI display (see its docstring) - it must
    NOT advance the sequence. Actual consumption happens only via
    SequenceService.next_value(), called internally from record creation
    (fill_autonumber_fields), not through this endpoint."""
    app_id, entity_id, headers = app_and_entity
    url = _seq_url(app_id, entity_id)

    create_r = await client.post(
        url,
        json={"field_name": "order_no", "prefix": "ORD-", "padding": 4, "step": 1},
        headers=headers,
    )
    seq_id = create_r.json()["id"]

    r1 = await client.post(f"{url}/{seq_id}/next", headers=headers)
    r2 = await client.post(f"{url}/{seq_id}/next", headers=headers)

    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert r1.json()["value"] == "ORD-0001"
    assert r2.json()["value"] == "ORD-0001"


@pytest.mark.asyncio
async def test_next_value_reflects_step_and_padding(client: AsyncClient, app_and_entity):
    app_id, entity_id, headers = app_and_entity
    url = _seq_url(app_id, entity_id)

    create_r = await client.post(
        url,
        json={"field_name": "order_no", "prefix": "S", "padding": 0, "step": 10},
        headers=headers,
    )
    seq_id = create_r.json()["id"]

    r1 = await client.post(f"{url}/{seq_id}/next", headers=headers)
    assert r1.json()["value"] == "S1"


@pytest.mark.asyncio
async def test_delete_sequence(client: AsyncClient, app_and_entity):
    app_id, entity_id, headers = app_and_entity
    url = _seq_url(app_id, entity_id)

    create_r = await client.post(url, json={"field_name": "order_no"}, headers=headers)
    seq_id = create_r.json()["id"]

    del_r = await client.delete(f"{url}/{seq_id}", headers=headers)
    assert del_r.status_code == 204, del_r.text

    get_r = await client.get(f"{url}/{seq_id}", headers=headers)
    assert get_r.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_field_name_rejected(client: AsyncClient, app_and_entity):
    app_id, entity_id, headers = app_and_entity
    url = _seq_url(app_id, entity_id)

    await client.post(url, json={"field_name": "order_no"}, headers=headers)
    r2 = await client.post(url, json={"field_name": "order_no"}, headers=headers)
    assert r2.status_code == 409, r2.text
